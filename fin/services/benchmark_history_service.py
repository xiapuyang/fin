"""Historical benchmark backfill: fills benchmark_results for past dates.

Runs once at server startup and nightly. For each active scheme (default,
custom, and a portfolio pseudo-scheme derived from current holdings), computes
XIRR on every trading day from the earliest deposit to yesterday. Skips dates
that already have a result row so re-runs are idempotent.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from fin.models.account import AccountModel
from fin.models.benchmark_result import BenchmarkResultModel
from fin.models.holding import HoldingModel
from fin.models.income import IncomeModel
from fin.models.transaction import TransactionModel
from fin.models.user import MOCK_USER_ID

logger = logging.getLogger(__name__)


def _price_on_date(series: list[dict], date: str) -> Optional[float]:
    """Return the exact close price for *date*, or None if the date is absent."""
    for entry in series:
        if entry["date"] == date:
            return entry["close"]
        if entry["date"] > date:
            break
    return None


def _trading_dates(
    scheme: dict, price_cache: dict, since: str, until: str
) -> list[str]:
    """Return sorted dates in [since, until] where all scheme symbols have prices.

    Uses intersection so every returned date has a valid price for every symbol,
    which avoids distorted terminal values from missing prices.
    """
    symbols = [a["symbol"] for a in scheme.get("allocations", [])]
    if not symbols:
        return []
    date_sets = []
    for sym in symbols:
        series = price_cache.get(sym, [])
        if not series:
            return []
        date_sets.append({e["date"] for e in series if since <= e["date"] <= until})
    common = date_sets[0]
    for s in date_sets[1:]:
        common &= s
    return sorted(common)


def _build_portfolio_scheme(
    db: Session,
    account: AccountModel,
    fx: dict,
    price_cache: dict,
) -> Optional[dict]:
    """Build a pseudo-scheme from current portfolio holdings proportions.

    Mirrors the delta computation in _compute_portfolio_xirr. Each equity
    symbol becomes an allocation weighted by its current USD value. Cash
    becomes cash_pct. Allocation pct values are % of investable (sum to 100)
    so simulate_scheme allocates 100% of each deposit.

    Returns None when holdings are empty or total value is zero.
    """
    from fin.services.benchmark_service import _fetch_current_price

    usd_rate = fx.get("USD", 7.2)

    holdings_all = (
        db.query(HoldingModel)
        .filter(
            HoldingModel.user_id == MOCK_USER_ID, HoldingModel.account == account.name
        )
        .all()
    )
    best: dict = {}
    for h in holdings_all:
        if h.code not in best or (h.snapshot_name or "") > (
            best[h.code].snapshot_name or ""
        ):
            best[h.code] = h
    if not best:
        return None

    # Apply post-snapshot transaction deltas (same logic as _compute_portfolio_xirr)
    transactions = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == MOCK_USER_ID,
            TransactionModel.account == account.name,
        )
        .order_by(TransactionModel.date)
        .all()
    )
    cutoff = account.cutoff_date or ""
    cash_currency = (best["CASH"].currency if "CASH" in best else "USD") or "USD"
    cash_fx = fx.get(cash_currency, 1.0)
    cash_snap = (best["CASH"].snapshot_name if "CASH" in best else "") or ""
    delta: dict = defaultdict(float)
    for t in transactions:
        if cutoff and t.date < cutoff:
            continue
        snap = (best[t.code].snapshot_name if t.code in best else "") or ""
        if t.date <= snap:
            continue
        delta[t.code] += t.shares if t.side == "buy" else -t.shares
        if t.code != "CASH" and "CASH" in best and t.date > cash_snap:
            cost = t.shares * t.price * fx.get(t.currency, 1.0) / cash_fx
            delta["CASH"] += -cost if t.side == "buy" else cost

    # Compute current USD value per holding
    values: dict = {}
    for code, h in best.items():
        live_shares = h.shares + delta.get(code, 0.0)
        if live_shares <= 0:
            continue
        if code == "CASH":
            price = 1.0
        else:
            series = price_cache.get(code, [])
            live = _fetch_current_price(code)
            price = live if live else (series[-1]["close"] if series else None)
        if price is None:
            continue
        values[code] = live_shares * price * fx.get(h.currency, 1.0) / usd_rate

    total_with_cash = sum(values.values())
    if total_with_cash <= 0:
        return None

    cash_val = values.pop("CASH", 0.0)
    equity_total = sum(values.values())
    if equity_total <= 0:
        return None

    # cash_pct = % of total kept as cash; pct = % of investable (sums to 100)
    cash_pct = round(cash_val / total_with_cash * 100, 4)
    allocations = [
        {"symbol": code, "pct": round(val / equity_total * 100, 4)}
        for code, val in values.items()
        if val > 0
    ]
    return {
        "id": "__portfolio__",
        "name": "Portfolio",
        "allocations": allocations,
        "cash_pct": cash_pct,
    }


def backfill_account(db: Session, account_id: int) -> int:
    """Compute and store missing historical benchmark results for *account_id*.

    Iterates every trading date between the earliest deposit and yesterday.
    Skips (bench_id, date) pairs that already have a row. Returns the number
    of new rows written.
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from fin.services.benchmark_service import (
        _fetch_fx,
        _resolve_schemes,
        simulate_scheme,
    )
    from fin.services.price_history_service import fetch_symbol

    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == MOCK_USER_ID)
        .first()
    )
    if account is None or account.benchmark_enabled != "1":
        return 0

    income = (
        db.query(IncomeModel)
        .filter(
            IncomeModel.user_id == MOCK_USER_ID,
            IncomeModel.account == account.name,
            IncomeModel.category.in_(["deposit", "withdrawal"]),
        )
        .order_by(IncomeModel.date)
        .all()
    )
    if not income:
        return 0

    earliest = income[0].date
    yesterday = str((datetime.now(timezone.utc) - timedelta(days=1)).date())
    if yesterday < earliest:
        return 0

    income_plain = [
        {
            "date": r.date,
            "currency": r.currency,
            "amount": r.amount,
            "category": r.category,
        }
        for r in income
    ]

    schemes = _resolve_schemes(db, account)
    fx = _fetch_fx(db)

    # Build price cache for all scheme symbols
    all_symbols: set = {a["symbol"] for s in schemes for a in s.get("allocations", [])}
    price_cache: dict = {}
    for sym in sorted(all_symbols):
        try:
            price_cache[sym] = fetch_symbol(db, sym, earliest)
        except Exception as exc:
            logger.warning("Backfill price fetch failed for %s: %s", sym, exc)
            price_cache[sym] = []

    # Add portfolio pseudo-scheme; fetch prices for any new symbols
    portfolio_scheme = _build_portfolio_scheme(db, account, fx, price_cache)
    all_schemes = list(schemes)
    if portfolio_scheme:
        for a in portfolio_scheme.get("allocations", []):
            sym = a["symbol"]
            if sym not in price_cache:
                try:
                    price_cache[sym] = fetch_symbol(db, sym, earliest)
                except Exception as exc:
                    logger.warning("Backfill price fetch failed for %s: %s", sym, exc)
                    price_cache[sym] = []
        all_schemes.append(portfolio_scheme)

    # Load existing (bench_id, date) pairs to skip
    existing = {
        (r[0], r[1])
        for r in db.execute(
            text(
                "SELECT bench_id, computed_date FROM benchmark_results "
                "WHERE account_id = :aid AND computed_date <= :until"
            ),
            {"aid": account_id, "until": yesterday},
        ).fetchall()
    }

    now_utc = datetime.now(timezone.utc)
    written = 0

    for scheme in all_schemes:
        bench_id = scheme["id"]
        dates = _trading_dates(scheme, price_cache, earliest, yesterday)

        for date in dates:
            if (bench_id, date) in existing:
                continue

            # Build prices at this date for terminal value
            current_prices_at: dict = {}
            for a in scheme.get("allocations", []):
                sym = a["symbol"]
                price = _price_on_date(price_cache.get(sym, []), date)
                if price is None:
                    break
                current_prices_at[sym] = price
            else:
                # All symbols had prices on this date
                try:
                    xirr_pct, _, terminal = simulate_scheme(
                        scheme,
                        income_plain,
                        price_cache,
                        current_prices_at,
                        fx,
                        terminal_date=date,
                    )
                except Exception as exc:
                    logger.debug(
                        "Backfill simulate_scheme failed %s %s: %s", bench_id, date, exc
                    )
                    continue

                if xirr_pct is None:
                    continue

                stmt = (
                    sqlite_insert(BenchmarkResultModel)
                    .values(
                        account_id=account_id,
                        bench_id=bench_id,
                        computed_date=date,
                        xirr=xirr_pct,
                        current_value_usd=terminal,
                        computed_at=now_utc,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["account_id", "bench_id", "computed_date"]
                    )
                )
                db.execute(stmt)
                written += 1
                existing.add((bench_id, date))

                if written % 500 == 0:
                    db.commit()
                    logger.debug(
                        "Backfill account %s: %d rows written so far",
                        account_id,
                        written,
                    )

    db.commit()
    logger.info("Backfill account %s: %d new rows written", account_id, written)
    return written


def backfill_all(db: Session) -> None:
    """Run backfill for every benchmark-enabled account."""
    accounts = (
        db.query(AccountModel)
        .filter(
            AccountModel.user_id == MOCK_USER_ID,
            AccountModel.benchmark_enabled == "1",
        )
        .all()
    )
    for account in accounts:
        try:
            n = backfill_account(db, account.id)
            if n:
                logger.info(
                    "Backfill: %d rows for account %s (%s)", n, account.id, account.name
                )
        except Exception:
            logger.exception("Backfill failed for account %s", account.id)
