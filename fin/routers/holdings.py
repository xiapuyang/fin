import csv
import io
import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from pydantic import Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fin.config import BULK_MAX_ITEMS, TS_FMT
from fin.database import get_db
from fin.models.account import AccountModel
from fin.models.holding import HoldingModel
from fin.models.dividend_history import DividendHistoryModel
from fin.models.income import IncomeModel
from fin.models.transaction import TransactionModel
from fin.models.user import MOCK_USER_ID
from fin.repositories.account_sqlite import AccountSQLiteRepository
from fin.repositories.holding_sqlite import HoldingSQLiteRepository
from fin.repositories.income_sqlite import IncomeSQLiteRepository
from fin.repositories.transaction_sqlite import TransactionSQLiteRepository
from fin.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from fin.schemas.bulk import BulkResponse
from fin.schemas.holding import HoldingCreate, HoldingResponse, HoldingUpdate
from fin.schemas.income import IncomeCreate, IncomeResponse, IncomeUpdate
from fin.schemas.transaction import (
    PagedTransactionResponse,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_DIVIDEND_INFO_TTL_HOURS = 24  # ex_date / annual_rate refresh cadence
_DIVIDEND_HIST_YEARS = 2  # how far back to pull on first fetch
_DIVIDEND_MAX_SYMBOLS = 50
_VALID_SYMBOL = re.compile(r"^[A-Z0-9.\-\^]{1,10}$")


def _account_response(a: AccountModel) -> AccountResponse:
    """Build an AccountResponse from an ORM model, deserializing JSON fields.

    Args:
        a: The AccountModel instance to convert.

    Returns:
        An AccountResponse with symbol_markets deserialized from JSON, or None
        if the column is absent or malformed.
    """
    sm = None
    if a.symbol_markets:
        try:
            sm = json.loads(a.symbol_markets)
        except json.JSONDecodeError:
            sm = None
    bs = None
    if a.benchmark_schemes:
        try:
            bs = json.loads(a.benchmark_schemes)
        except json.JSONDecodeError:
            bs = None
    return AccountResponse(
        id=a.id,
        name=a.name,
        currency=a.currency or "CNY",
        note=a.note,
        cutoff_date=a.cutoff_date,
        balance_account_id=a.balance_account_id,
        balance_sub_account_id=a.balance_sub_account_id,
        symbol_markets=sm,
        benchmark_enabled=a.benchmark_enabled == "1",
        benchmark_schemes=bs,
        create_time=a.create_time.strftime(TS_FMT),
        update_time=a.update_time.strftime(TS_FMT),
    )


def _holding_response(h: HoldingModel) -> HoldingResponse:
    """Convert a HoldingModel ORM instance to a HoldingResponse schema.

    Args:
        h: ORM model instance.

    Returns:
        HoldingResponse schema instance.
    """
    return HoldingResponse(
        id=h.id,
        code=h.code,
        name=h.name,
        market=h.market,
        currency=h.currency,
        account=h.account,
        snapshot_name=h.snapshot_name,
        shares=h.shares,
        avg_cost=h.avg_cost,
        note=h.note,
        create_time=h.create_time.strftime(TS_FMT),
        update_time=h.update_time.strftime(TS_FMT),
    )


def _tx_response(t: TransactionModel) -> TransactionResponse:
    """Convert a TransactionModel ORM instance to a TransactionResponse schema.

    Args:
        t: ORM model instance.

    Returns:
        TransactionResponse schema instance.
    """
    return TransactionResponse(
        id=t.id,
        date=t.date,
        code=t.code,
        name=t.name,
        side=t.side,
        shares=t.shares,
        price=t.price,
        currency=t.currency,
        account=t.account,
        realized=t.realized,
        note=t.note,
        create_time=t.create_time.strftime(TS_FMT),
        update_time=t.update_time.strftime(TS_FMT),
    )


def _income_response(i: IncomeModel) -> IncomeResponse:
    """Convert an IncomeModel ORM instance to an IncomeResponse schema.

    Args:
        i: ORM model instance.

    Returns:
        IncomeResponse schema instance.
    """
    return IncomeResponse(
        id=i.id,
        date=i.date,
        source=i.source,
        category=i.category,
        amount=i.amount,
        currency=i.currency,
        account=i.account,
        code=i.code,
        note=i.note,
        create_time=i.create_time.strftime(TS_FMT),
        update_time=i.update_time.strftime(TS_FMT),
    )


def _parse_dollar(s: str) -> float:
    """Parse dollar-format string like '$1,740.00' or '-$37.00' to float."""
    s = s.strip()
    if not s:
        return 0.0
    negative = s.startswith("-")
    s = s.lstrip("-").lstrip("$").replace(",", "")
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return 0.0


def _parse_notion_row(row: dict) -> tuple[TransactionCreate | None, str]:
    """Parse one Notion CSV row into TransactionCreate. Returns (obj, error_reason)."""
    try:
        raw_name = row.get("Name", "").strip()
        # Prefer explicit SYMBOL column (normalized CSV); fall back to first token of Name
        symbol_col = row.get("SYMBOL", "").strip().upper()
        code = (
            symbol_col
            if symbol_col
            else (raw_name.split()[0].upper() if raw_name else "UNKNOWN")
        )
        side_raw = row.get("交易", "").strip()
        side = "buy" if side_raw == "买" else "sell" if side_raw == "卖" else None
        if side is None:
            return None, f"unknown 交易 value: {side_raw!r}"

        price_str = row.get("买卖价格", "").strip()
        shares_str = row.get("买卖数量", "").strip()
        realized_str = row.get("卖出盈利", "").strip()
        date_str = row.get("日期", "").strip()

        price = _parse_dollar(price_str) if price_str else 0.0
        shares = float(shares_str) if shares_str else 0.0

        realized: float | None = None
        if realized_str:
            realized = _parse_dollar(realized_str)

        # Parse "March 19, 2024" → "2024-03-19"
        date = datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")

        note = raw_name if raw_name != code else None
        if realized is not None and (shares == 0 or price == 0):
            # Funds/rows with only realized profit — store in note
            note = f"{raw_name} 卖出盈利: {realized_str}"

        return TransactionCreate(
            date=date,
            code=code,
            name=raw_name,
            side=side,
            shares=shares,
            price=price,
            currency="USD",
            realized=realized,
            note=note,
        ), ""
    except Exception as exc:
        return None, str(exc)


# ── Accounts ────────────────────────────────────────────────────────────────


@router.get("/accounts", response_model=list[AccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    return [
        _account_response(a) for a in AccountSQLiteRepository(db).get_all(MOCK_USER_ID)
    ]


@router.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    return _account_response(AccountSQLiteRepository(db).create(data, MOCK_USER_ID))


@router.put("/accounts/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, data: AccountUpdate, db: Session = Depends(get_db)):
    try:
        updated = AccountSQLiteRepository(db).update(account_id, data, MOCK_USER_ID)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Account name already exists")
    if updated is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return _account_response(updated)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    AccountSQLiteRepository(db).delete(account_id, MOCK_USER_ID)
    return Response(status_code=204)


# ── Holdings (positions) ────────────────────────────────────────────────────


@router.get("/holdings", response_model=list[HoldingResponse])
def list_holdings(db: Session = Depends(get_db)):
    repo = HoldingSQLiteRepository(db)
    return [_holding_response(h) for h in repo.get_all(MOCK_USER_ID)]


@router.post("/holdings/bulk", response_model=BulkResponse, status_code=201)
def bulk_create_holdings(
    items: Annotated[list[HoldingCreate], Field(max_length=BULK_MAX_ITEMS)],
    db: Session = Depends(get_db),
):
    """Bulk-create holdings. All-or-nothing on validation; duplicates skipped.

    Dedup key is `(account, code, snapshot_name)` (matches `uq_holding_snapshot`)
    and is pre-filtered against both existing rows and earlier rows in the same
    input batch. Validation errors on any item short-circuit with 422 before any
    insert (FastAPI handles this via the `list[HoldingCreate]` body annotation).
    """
    repo = HoldingSQLiteRepository(db)
    created_models, skipped = repo.bulk_create(items, user_id=MOCK_USER_ID)
    return BulkResponse(created=len(created_models), skipped=skipped)


@router.post("/holdings", response_model=HoldingResponse, status_code=201)
def create_holding(data: HoldingCreate, db: Session = Depends(get_db)):
    repo = HoldingSQLiteRepository(db)
    return _holding_response(repo.create(data, MOCK_USER_ID))


@router.put("/holdings/{holding_id}", response_model=HoldingResponse)
def update_holding(holding_id: int, data: HoldingUpdate, db: Session = Depends(get_db)):
    repo = HoldingSQLiteRepository(db)
    try:
        return _holding_response(repo.update(holding_id, data, MOCK_USER_ID))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    HoldingSQLiteRepository(db).delete(holding_id, MOCK_USER_ID)
    return Response(status_code=204)


# ── Transactions ────────────────────────────────────────────────────────────


@router.post("/transactions/import")
async def import_transactions(file: UploadFile, db: Session = Depends(get_db)):
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))

    valid: list[TransactionCreate] = []
    skipped: list[dict] = []

    for i, row in enumerate(reader):
        txn, reason = _parse_notion_row(row)
        if txn is None:
            skipped.append({"row": i, "reason": reason})
        else:
            valid.append(txn)

    repo = TransactionSQLiteRepository(db)
    imported = repo.bulk_create(valid, MOCK_USER_ID)
    logger.info("CSV import: %d imported, %d skipped", len(imported), len(skipped))
    return {"imported": len(imported), "skipped": skipped}


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(db: Session = Depends(get_db)):
    repo = TransactionSQLiteRepository(db)
    return [_tx_response(t) for t in repo.get_all(MOCK_USER_ID)]


@router.get("/transactions/paged", response_model=PagedTransactionResponse)
def list_transactions_paged(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    symbol: str | None = Query(None),
    account: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Return a paginated page of transactions for the current user.

    Args:
        page: 1-based page number.
        page_size: Number of rows per page (1-200, default 30).
        symbol: Optional ticker code filter (exact match).
        account: Optional account name filter (exact match).
        db: Database session (injected).

    Returns:
        PagedTransactionResponse with items and total count.
    """
    repo = TransactionSQLiteRepository(db)
    items, total = repo.get_page(MOCK_USER_ID, page, page_size, symbol, account)
    return {"items": [_tx_response(t) for t in items], "total": total}


@router.post("/transactions/bulk", response_model=BulkResponse, status_code=201)
def bulk_create_transactions(
    items: Annotated[list[TransactionCreate], Field(max_length=BULK_MAX_ITEMS)],
    db: Session = Depends(get_db),
):
    """Bulk-create transactions. All-or-nothing on validation; duplicates skipped.

    Reuses the existing `bulk_create()` repo method which dedups on the
    `uq_txn_dedup` unique constraint `(user_id, date, code, side, shares,
    price, currency)` via SQLite `ON CONFLICT DO NOTHING`. Validation errors
    on any item short-circuit with 422 before any insert (FastAPI handles
    this via the `list[TransactionCreate]` body annotation).
    """
    repo = TransactionSQLiteRepository(db)
    created = repo.bulk_create(items, user_id=MOCK_USER_ID)
    return BulkResponse(created=len(created), skipped=len(items) - len(created))


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
def create_transaction(data: TransactionCreate, db: Session = Depends(get_db)):
    repo = TransactionSQLiteRepository(db)
    return _tx_response(repo.create(data, MOCK_USER_ID))


@router.put("/transactions/{txn_id}", response_model=TransactionResponse)
def update_transaction(
    txn_id: int, data: TransactionUpdate, db: Session = Depends(get_db)
):
    repo = TransactionSQLiteRepository(db)
    try:
        return _tx_response(repo.update(txn_id, data, MOCK_USER_ID))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, db: Session = Depends(get_db)):
    TransactionSQLiteRepository(db).delete(txn_id, MOCK_USER_ID)
    return Response(status_code=204)


# ── Income ──────────────────────────────────────────────────────────────────


@router.get("/income", response_model=list[IncomeResponse])
def list_income(db: Session = Depends(get_db)):
    repo = IncomeSQLiteRepository(db)
    return [_income_response(i) for i in repo.get_all(MOCK_USER_ID)]


@router.post("/income", response_model=IncomeResponse, status_code=201)
def create_income(data: IncomeCreate, db: Session = Depends(get_db)):
    repo = IncomeSQLiteRepository(db)
    return _income_response(repo.create(data, MOCK_USER_ID))


@router.post("/income/bulk", response_model=BulkResponse, status_code=201)
def bulk_create_income(
    items: Annotated[list[IncomeCreate], Field(max_length=BULK_MAX_ITEMS)],
    db: Session = Depends(get_db),
):
    """Bulk-create income records. All-or-nothing on validation; duplicates skipped.

    Reuses the existing `bulk_create()` repo method which dedups on the
    `uq_income_dedup` unique constraint `(user_id, date, source, amount,
    currency)` via SQLite `ON CONFLICT DO NOTHING`. Validation errors on any
    item short-circuit with 422 before any insert (FastAPI handles this via
    the `list[IncomeCreate]` body annotation).
    """
    repo = IncomeSQLiteRepository(db)
    created = repo.bulk_create(items, user_id=MOCK_USER_ID)
    return BulkResponse(created=len(created), skipped=len(items) - len(created))


@router.put("/income/{income_id}", response_model=IncomeResponse)
def update_income(income_id: int, data: IncomeUpdate, db: Session = Depends(get_db)):
    repo = IncomeSQLiteRepository(db)
    try:
        return _income_response(repo.update(income_id, data, MOCK_USER_ID))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/income/{income_id}", status_code=204)
def delete_income(income_id: int, db: Session = Depends(get_db)):
    IncomeSQLiteRepository(db).delete(income_id, MOCK_USER_ID)
    return Response(status_code=204)


@router.post("/income/import")
async def import_income(
    file: UploadFile,
    account: str = Query(default=None),
    db: Session = Depends(get_db),
):
    """Import income records from an IBKR deposit CSV export.

    Args:
        file: CSV file (utf-8-sig or GBK). Expected columns: date=0, ref=1,
            method=2, amount=12 (format: 'USD 1,234.56'), status=13.
            Only rows where status == '可用' are imported.
        account: Account name to tag all imported records.
        db: Database session.

    Returns:
        Dict with imported count, skipped rows with reasons, and full income list.
    """
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="replace")

    reader = csv.reader(io.StringIO(text))
    next(reader, None)  # skip header

    valid: list[IncomeCreate] = []
    skipped: list[dict] = []

    for i, row in enumerate(reader):
        if not row or not row[0].strip():
            continue
        if len(row) < 14:
            skipped.append({"row": i, "reason": f"too few columns ({len(row)})"})
            continue
        try:
            date = row[0].strip()
            ref = row[1].strip()
            method = row[2].strip()
            raw_amount = row[12].strip().strip('"')
            status = row[13].strip()

            if status != "可用":
                skipped.append({"row": i, "reason": f"status={status}"})
                continue

            # parse "USD 65,000.00" → ("USD", 65000.0)
            parts = raw_amount.split(None, 1)
            if len(parts) != 2:
                skipped.append({"row": i, "reason": f"bad amount: {raw_amount}"})
                continue
            currency = parts[0]
            amount = float(parts[1].replace(",", ""))
            if not math.isfinite(amount):
                skipped.append({"row": i, "reason": f"non-finite amount: {raw_amount}"})
                continue

            valid.append(
                IncomeCreate(
                    date=date,
                    source=f"{method} {ref}",
                    category="deposit",
                    amount=amount,
                    currency=currency,
                    account=account or None,
                )
            )
        except (IndexError, ValueError) as e:
            skipped.append({"row": i, "reason": str(e)})

    repo = IncomeSQLiteRepository(db)
    imported = repo.bulk_create(valid, MOCK_USER_ID)
    all_income = repo.get_all(MOCK_USER_ID)
    logger.info(
        "Income CSV import: %d imported, %d skipped", len(imported), len(skipped)
    )
    return {
        "imported": len(imported),
        "skipped": skipped,
        "income": [_income_response(i) for i in all_income],
    }


def _yf_parse_info(info: dict[str, Any]) -> tuple[str | None, str | None, float | None]:
    """Extract (ex_date, pay_date, annual_rate) from a yfinance info dict."""
    ex_ts = info.get("exDividendDate")
    ex_date = (
        datetime.fromtimestamp(ex_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if ex_ts
        else None
    )
    pay_ts = info.get("dividendDate")
    pay_date = (
        datetime.fromtimestamp(pay_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if pay_ts
        else None
    )
    return ex_date, pay_date, info.get("dividendRate")


def _annual_rate_from_history(history: list[dict]) -> float | None:
    """Sum of actual dividend payments in the last 365 days.

    Used as a fallback when yfinance does not provide dividendRate (common for
    bond ETFs and broad-market ETFs that pay monthly or irregularly).
    """
    if not history:
        return None
    one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).strftime(
        "%Y-%m-%d"
    )
    total = sum(h["amount"] for h in history if h["date"] >= one_year_ago)
    return round(total, 4) if total > 0 else None


def _yf_fetch_history(ticker: yf.Ticker, since: datetime) -> list[dict]:
    """Return dividend history entries on or after *since* as [{date, amount}]."""
    hist = ticker.dividends
    if hist.empty:
        return []
    idx = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
    since_naive = since.replace(tzinfo=None)
    return [
        {"date": str(d.date()), "amount": round(float(a), 4)}
        for d, a in zip(idx, hist.values)
        if d >= since_naive
    ]


def _parse_fetched_at(ts: str) -> datetime:
    """Parse a fetched_at ISO string; treats naive timestamps as UTC."""
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_history_json(raw: str | None) -> list[dict]:
    """Safely deserialise a history_json column value; returns [] on any error."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _fetch_one(
    code: str, existing_json: str | None, now: datetime
) -> tuple[str, dict | None]:
    """Fetch yfinance data for one symbol; returns (code, data) or (code, None) on failure."""
    try:
        ticker = yf.Ticker(code)
        if not ticker.info:
            # Empty info dict signals a transient rate-limit or unavailability.
            # Returning None prevents caching an empty record for 24 h.
            return code, None
        ex_date, pay_date, annual_rate = _yf_parse_info(ticker.info)
        if existing_json is not None:
            existing = _parse_history_json(existing_json)
            last_date = max((e["date"] for e in existing), default=None)
            since = (
                (datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1))
                if last_date
                else (now - timedelta(days=90))
            )
            history = existing + _yf_fetch_history(ticker, since)
        else:
            history = _yf_fetch_history(
                ticker, now - timedelta(days=_DIVIDEND_HIST_YEARS * 365)
            )
        effective_rate = annual_rate or _annual_rate_from_history(history)
        return code, {
            "ex_date": ex_date,
            "pay_date": pay_date,
            "annual_rate": effective_rate,
            "history": history,
        }
    except Exception:
        logger.warning("dividend fetch failed for %s", code, exc_info=True)
        return code, None


def _refresh_stale_dividends(
    stale_codes: list[str],
    rows_data: dict[str, str | None],
    rows: dict,
    db: Session,
    now: datetime,
) -> dict[str, dict]:
    """Fetch and persist dividend data for stale/missing symbols; returns result slice."""
    result: dict[str, dict] = {}
    pool = ThreadPoolExecutor(max_workers=min(len(stale_codes), 8))
    try:
        futures = {
            pool.submit(_fetch_one, code, rows_data[code], now): code
            for code in stale_codes
        }
        processed: set[str] = set()
        try:
            for future in as_completed(futures, timeout=20):
                code, data = future.result()
                if code in processed:  # guard against re-yield after timeout
                    continue
                processed.add(code)
                row = rows.get(code)
                if data:
                    if row:
                        row.ex_date = data["ex_date"]
                        row.pay_date = data["pay_date"]
                        row.annual_rate = data["annual_rate"]
                        row.history_json = json.dumps(data["history"])
                        row.fetched_at = now.isoformat()
                    else:
                        # Savepoint so a concurrent duplicate INSERT only rolls back
                        # this symbol, not all the updates from this request.
                        try:
                            with db.begin_nested():
                                db.add(
                                    DividendHistoryModel(
                                        symbol=code,
                                        ex_date=data["ex_date"],
                                        pay_date=data["pay_date"],
                                        annual_rate=data["annual_rate"],
                                        history_json=json.dumps(data["history"]),
                                        fetched_at=now.isoformat(),
                                    )
                                )
                        except IntegrityError:
                            pass  # concurrent request already inserted this symbol
                    if data["ex_date"] or data["history"]:
                        result[code] = data
                elif row:
                    # yfinance failed — return stale DB data; fetched_at NOT updated
                    # so the symbol is retried on the next request.
                    history = _parse_history_json(row.history_json)
                    if row.ex_date or history:
                        result[code] = {
                            "ex_date": row.ex_date,
                            "pay_date": row.pay_date,
                            "annual_rate": row.annual_rate,
                            "history": history,
                        }
        except TimeoutError:
            timed_out = [c for f, c in futures.items() if c not in processed]
            logger.warning(
                "dividend fetch timed out; %d symbol(s) incomplete: %s",
                len(timed_out),
                timed_out,
            )
            for code in timed_out:
                row = rows.get(code)
                if row:
                    history = _parse_history_json(row.history_json)
                    if row.ex_date or history:
                        result[code] = {
                            "ex_date": row.ex_date,
                            "pay_date": row.pay_date,
                            "annual_rate": row.annual_rate,
                            "history": history,
                        }
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    db.commit()
    return result


@router.get("/dividends")
def get_dividends(symbols: str = Query(""), db: Session = Depends(get_db)):
    """Return dividend history and next ex-date for a comma-separated list of symbols.

    Strategy:
    - History (ticker.dividends): fetched once on first DB write, then only new
      entries (last 90 days) are appended on each info refresh.
    - Forward info (ex_date, pay_date, annual_rate): refreshed every 24 h via
      ticker.info, which is faster than a full history pull.
    """
    codes = list(
        dict.fromkeys(
            s.strip().upper()
            for s in symbols.split(",")
            if s.strip() and s.strip().upper() != "CASH"
        )
    )
    if not codes:
        return {}
    if len(codes) > _DIVIDEND_MAX_SYMBOLS:
        raise HTTPException(
            status_code=422, detail=f"Too many symbols (max {_DIVIDEND_MAX_SYMBOLS})"
        )
    codes = [c for c in codes if _VALID_SYMBOL.match(c)]
    if not codes:
        return {}

    now = datetime.now(timezone.utc)
    info_stale_threshold = now - timedelta(hours=_DIVIDEND_INFO_TTL_HOURS)
    rows = {
        r.symbol: r
        for r in db.query(DividendHistoryModel)
        .filter(DividendHistoryModel.symbol.in_(codes))
        .all()
    }

    result: dict[str, dict] = {}
    stale_codes: list[str] = []

    for code in codes:
        row = rows.get(code)
        info_fresh = (
            row
            and row.fetched_at
            and _parse_fetched_at(row.fetched_at) >= info_stale_threshold
        )
        if info_fresh:
            history = _parse_history_json(row.history_json)
            annual_rate = row.annual_rate or _annual_rate_from_history(history)
            if row.ex_date or history:
                result[code] = {
                    "ex_date": row.ex_date,
                    "pay_date": row.pay_date,
                    "annual_rate": annual_rate,
                    "history": history,
                }
        else:
            stale_codes.append(code)

    if stale_codes:
        rows_data: dict[str, str | None] = {
            code: rows[code].history_json if code in rows else None
            for code in stale_codes
        }
        result.update(_refresh_stale_dividends(stale_codes, rows_data, rows, db, now))

    return result
