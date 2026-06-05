"""Historical benchmark backfill: fills benchmark_results for past dates.

Runs once at server startup and nightly. For each active scheme (default,
custom, and a portfolio pseudo-scheme derived from current holdings), computes
XIRR on every trading day from the earliest deposit to yesterday. Skips dates
that already have a result row so re-runs are idempotent.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from fin.config import APP_CONFIG_PATH
from fin.models.account import AccountModel
from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
from fin.models.benchmark_result import BenchmarkResultModel
from fin.models.income import IncomeModel
from fin.models.user import MOCK_USER_ID

logger = logging.getLogger(__name__)


def _price_on_date(series: list[dict], date: str) -> Optional[float]:
    """Return the exact close price for *date*, or None if the date is absent."""
    lo, hi = 0, len(series) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        d = series[mid]["date"]
        if d == date:
            return series[mid]["close"]
        elif d < date:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


def _code_to_yf_symbol(code: str) -> str:
    from fin.services.quote import normalize_symbol

    return normalize_symbol(code)


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

    Each equity symbol becomes an allocation weighted by its current USD value.
    Cash becomes cash_pct. Allocation pct values are % of investable (sum to 100)
    so simulate_scheme allocates 100% of each deposit.

    Returns None when holdings are empty or total value is zero.
    """
    from fin.services.benchmark_service import (
        _build_holdings_positions,
        _holding_current_price,
    )

    usd_rate = fx.get("USD", 7.2)
    positions = _build_holdings_positions(db, account, fx)
    if not positions:
        return None

    values: dict = {}
    for code, (live_shares, h) in positions.items():
        if code == "CASH":
            price = 1.0
        else:
            series = price_cache.get(code, [])
            price = _holding_current_price(db, code, series)
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

    cash_pct = round(cash_val / total_with_cash * 100, 4)
    equity_fraction = (100 - cash_pct) / 100
    allocations = [
        {
            "symbol": _code_to_yf_symbol(code),
            "pct": round(val / equity_total * equity_fraction * 100, 4),
        }
        for code, val in values.items()
        if val > 0
    ]
    return {
        "id": "__portfolio__",
        "name": "Portfolio",
        "allocations": allocations,
        "cash_pct": cash_pct,
    }


def _fix_stale_snapshot_allocations(db: Session, account_id: int) -> None:
    """Rescale stale snapshot allocations so sum(alloc.pct) + cash_pct == 100%.

    Snapshots created before the equity-fraction fix stored alloc.pct summing to
    100% regardless of cash_pct, so total exceeded 100%. This function detects
    and corrects those rows in-place.
    """
    snaps = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account_id,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 1,
        )
        .all()
    )
    for snap in snaps:
        allocs = json.loads(snap.allocations_json)
        total = sum(a["pct"] for a in allocs) + snap.cash_pct
        if total <= 100.01:
            continue
        # Rescale: equity portion should be 100 - cash_pct
        expected_equity = 100.0 - snap.cash_pct
        actual_equity = sum(a["pct"] for a in allocs)
        if actual_equity <= 0:
            continue
        scale = expected_equity / actual_equity
        fixed = [
            {"symbol": a["symbol"], "pct": round(a["pct"] * scale, 4)} for a in allocs
        ]
        snap.allocations_json = json.dumps(fixed)
        logger.info(
            "Fixed stale allocation for snapshot %s (was %.4f%%, now %.4f%%)",
            snap.name,
            total,
            sum(a["pct"] for a in fixed) + snap.cash_pct,
        )
    db.commit()


def _get_or_create_portfolio_snapshot(
    db: Session,
    account_id: int,
    portfolio_scheme: dict,
    snap_date: str,
    interval_days: int = 30,
) -> BenchmarkCustomSchemeModel:
    """Get or create a portfolio composition snapshot for *snap_date*.

    Compares allocations + cash_pct against the most recent snapshot. If
    unchanged, returns the existing record so backfill reuses its bench_id
    without creating duplicate rows.
    """
    new_allocs = json.dumps(
        sorted(portfolio_scheme["allocations"], key=lambda a: a["symbol"])
    )
    new_cash = round(portfolio_scheme.get("cash_pct", 0.0), 4)

    latest = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account_id,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 1,
        )
        .order_by(BenchmarkCustomSchemeModel.id.desc())
        .first()
    )

    if latest is not None:
        # Only create a new snapshot once per month at most, even if composition changed.
        # Daily backfill incrementally extends the latest snapshot's historical curve.
        try:
            latest_date_str = (
                latest.name.split("Portfolio ", 1)[1].split(" ")[0]
                if latest.name.startswith("Portfolio ")
                else ""
            )
            latest_snap_dt = datetime.strptime(latest_date_str, "%Y-%m-%d").date()
            snap_dt = datetime.strptime(snap_date, "%Y-%m-%d").date()
            if (snap_dt - latest_snap_dt).days < interval_days:
                return latest
        except (ValueError, IndexError):
            pass

        existing_allocs = json.dumps(
            sorted(json.loads(latest.allocations_json), key=lambda a: a["symbol"])
        )
        if existing_allocs == new_allocs and abs(latest.cash_pct - new_cash) < 0.01:
            return latest

    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    stmt = (
        sqlite_insert(BenchmarkCustomSchemeModel)
        .values(
            account_id=account_id,
            name=f"Portfolio {snap_date}",
            allocations_json=new_allocs,
            cash_pct=new_cash,
            enabled=1,
            is_portfolio_snapshot=1,
        )
        .on_conflict_do_nothing(index_elements=["account_id", "name"])
    )
    db.execute(stmt)
    db.commit()

    row = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account_id,
            BenchmarkCustomSchemeModel.name == f"Portfolio {snap_date}",
        )
        .first()
    )
    logger.info(
        "Portfolio snapshot created for account %s on %s", account_id, snap_date
    )
    return row


def _build_backfill_price_cache(
    db: Session, schemes: list[dict], earliest: str
) -> dict[str, list[dict]]:
    """Fetch price history for all symbols referenced by *schemes*."""
    from fin.services.price_history_service import fetch_symbol

    all_symbols: set = {a["symbol"] for s in schemes for a in s.get("allocations", [])}
    price_cache: dict = {}
    for sym in sorted(all_symbols):
        try:
            price_cache[sym] = fetch_symbol(db, sym, earliest)
        except Exception as exc:
            logger.warning("Backfill price fetch failed for %s: %s", sym, exc)
            price_cache[sym] = []
    return price_cache


def _collect_portfolio_snapshot_schemes(
    db: Session,
    account: AccountModel,
    fx: dict,
    price_cache: dict,
    base_schemes: list[dict],
    yesterday: str,
    snapshot_interval: int,
    earliest: str,
) -> list[dict]:
    """Build the full list of schemes for backfill, including portfolio snapshots.

    Creates a new portfolio composition snapshot if the interval has elapsed,
    then returns base_schemes plus one entry per enabled portfolio snapshot.
    """
    from fin.services.price_history_service import fetch_symbol

    portfolio_scheme = _build_portfolio_scheme(db, account, fx, price_cache)
    if portfolio_scheme:
        for a in portfolio_scheme.get("allocations", []):
            sym = a["symbol"]
            if sym not in price_cache:
                try:
                    price_cache[sym] = fetch_symbol(db, sym, earliest)
                except Exception as exc:
                    logger.warning("Backfill price fetch failed for %s: %s", sym, exc)
                    price_cache[sym] = []
        _get_or_create_portfolio_snapshot(
            db, account.id, portfolio_scheme, yesterday, interval_days=snapshot_interval
        )

    existing_snaps = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account.id,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 1,
            BenchmarkCustomSchemeModel.enabled != 0,
        )
        .all()
    )
    all_schemes = list(base_schemes)
    for snap_row in existing_snaps:
        snap_allocs = json.loads(snap_row.allocations_json)
        snap_allocs = [
            {**a, "symbol": _code_to_yf_symbol(a["symbol"])} for a in snap_allocs
        ]
        for a in snap_allocs:
            sym = a["symbol"]
            if sym not in price_cache:
                try:
                    price_cache[sym] = fetch_symbol(db, sym, earliest)
                except Exception as exc:
                    logger.warning("Backfill price fetch failed for %s: %s", sym, exc)
                    price_cache[sym] = []
        all_schemes.append(
            {
                "id": str(snap_row.id),
                "name": snap_row.name,
                "allocations": snap_allocs,
                "cash_pct": snap_row.cash_pct,
            }
        )
    return all_schemes


def _backfill_scheme_dates(
    db: Session,
    account_id: int,
    scheme: dict,
    income_plain: list[dict],
    price_cache: dict,
    fx: dict,
    existing: set,
    now_utc: datetime,
    earliest: str,
    yesterday: str,
) -> int:
    """Write missing benchmark_results rows for *scheme* across all trading dates.

    Returns the number of new rows written.
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from fin.services.benchmark_service import simulate_scheme

    bench_id = scheme["id"]
    dates = _trading_dates(scheme, price_cache, earliest, yesterday)
    written = 0

    for date in dates:
        if (bench_id, date) in existing:
            continue

        current_prices_at: dict = {}
        for a in scheme.get("allocations", []):
            sym = a["symbol"]
            price = _price_on_date(price_cache.get(sym, []), date)
            if price is None:
                break
            current_prices_at[sym] = price
        else:
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
                    "Backfill account %s: %d rows written so far", account_id, written
                )

    return written


def backfill_account(db: Session, account_id: int) -> int:
    """Compute and store missing historical benchmark results for *account_id*.

    Iterates every trading date between the earliest deposit and yesterday.
    Skips (bench_id, date) pairs that already have a row. Returns the number
    of new rows written.
    """
    _fix_stale_snapshot_allocations(db, account_id)

    from fin.services.benchmark_service import (
        _fetch_fx,
        _resolve_schemes,
        _serialize_income,
    )

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

    income_plain = _serialize_income(income)
    schemes = _resolve_schemes(db, account)
    fx = _fetch_fx(db)
    price_cache = _build_backfill_price_cache(db, schemes, earliest)

    try:
        _cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        snapshot_interval = int(_cfg.get("benchmark_snapshot_interval_days", 30))
    except Exception:
        snapshot_interval = 30

    all_schemes = _collect_portfolio_snapshot_schemes(
        db, account, fx, price_cache, schemes, yesterday, snapshot_interval, earliest
    )

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
        written += _backfill_scheme_dates(
            db,
            account_id,
            scheme,
            income_plain,
            price_cache,
            fx,
            existing,
            now_utc,
            earliest,
            yesterday,
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
