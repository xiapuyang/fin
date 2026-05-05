import csv
import io
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from fin.database import get_db
from fin.models.account import AccountModel
from fin.models.holding import HoldingModel
from fin.models.income import IncomeModel
from fin.models.transaction import TransactionModel
from fin.models.user import MOCK_USER_ID
from fin.repositories.account_sqlite import AccountSQLiteRepository
from fin.repositories.holding_sqlite import HoldingSQLiteRepository
from fin.repositories.income_sqlite import IncomeSQLiteRepository
from fin.repositories.transaction_sqlite import TransactionSQLiteRepository
from fin.schemas.account import AccountCreate, AccountResponse
from fin.schemas.holding import HoldingCreate, HoldingResponse, HoldingUpdate
from fin.schemas.income import IncomeCreate, IncomeResponse, IncomeUpdate
from fin.schemas.transaction import (
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _account_response(a: AccountModel) -> AccountResponse:
    return AccountResponse(
        id=a.id,
        name=a.name,
        currency=a.currency or "CNY",
        note=a.note,
        create_time=a.create_time.strftime(_TS_FMT),
        update_time=a.update_time.strftime(_TS_FMT),
    )


def _holding_response(h: HoldingModel) -> HoldingResponse:
    return HoldingResponse(
        id=h.id,
        code=h.code,
        name=h.name,
        market=h.market,
        currency=h.currency,
        account=h.account,
        snapshot_name=h.snapshot_name,
        as_of_date=h.as_of_date,
        shares=h.shares,
        avg_cost=h.avg_cost,
        note=h.note,
        create_time=h.create_time.strftime(_TS_FMT),
        update_time=h.update_time.strftime(_TS_FMT),
    )


def _tx_response(t: TransactionModel) -> TransactionResponse:
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
        create_time=t.create_time.strftime(_TS_FMT),
        update_time=t.update_time.strftime(_TS_FMT),
    )


def _income_response(i: IncomeModel) -> IncomeResponse:
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
        create_time=i.create_time.strftime(_TS_FMT),
        update_time=i.update_time.strftime(_TS_FMT),
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


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    AccountSQLiteRepository(db).delete(account_id)
    return Response(status_code=204)


# ── Holdings (positions) ────────────────────────────────────────────────────


@router.get("/holdings", response_model=list[HoldingResponse])
def list_holdings(db: Session = Depends(get_db)):
    repo = HoldingSQLiteRepository(db)
    return [_holding_response(h) for h in repo.get_all(MOCK_USER_ID)]


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
    content = await file.read()
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
        try:
            date = row[0].strip()
            ref = row[1].strip()
            method = row[2].strip()
            raw_amount = row[12].strip().strip('"')
            status = row[13].strip() if len(row) > 13 else ""

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
        except Exception as e:
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
