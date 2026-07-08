import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from fin.config import APP_CONFIG_PATH
from fin.models.account import AccountModel
from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
from fin.models.benchmark_result import BenchmarkResultModel
from fin.models.holding import HoldingModel
from fin.models.income import IncomeModel
from fin.models.transaction import TransactionModel
from fin.models.user import MOCK_USER_ID
from fin.services.price_history_service import fetch_symbol

logger = logging.getLogger(__name__)

_NEAREST_PRICE_WINDOW_DAYS = 10  # covers Chinese New Year holiday gap
_DEFAULTS_CACHE: Optional[list] = None
_FX_PAIRS = {"USD": "USDCNY=X", "HKD": "HKDCNY=X", "CAD": "CADCNY=X"}
_PORTFOLIO_BENCH_ID = "__portfolio__"


# ── XIRR (Newton-Raphson) ─────────────────────────────────────────────────────


def xirr(flows: list[tuple[str, float]]) -> Optional[float]:
    """Compute XIRR from a list of (date_str, amount) tuples.

    Negative amount = outflow (deposit). Positive = inflow (withdrawal / terminal).

    Args:
        flows: List of (date_str "YYYY-MM-DD", float) sorted by date.

    Returns:
        Annualized return as a percentage (e.g. 8.5 for 8.5%), or None if
        the calculation cannot converge or lacks valid cash flows.
    """
    if len(flows) < 2:
        return None
    amounts = [f[1] for f in flows]
    if not any(a < 0 for a in amounts):
        return None
    if not any(a > 0 for a in amounts):
        return None

    t0 = datetime.strptime(flows[0][0], "%Y-%m-%d")
    years = [(datetime.strptime(f[0], "%Y-%m-%d") - t0).days / 365.25 for f in flows]
    if max(years) < 1e-9:
        return None

    def _npv(r: float) -> float:
        return sum(amt / (1 + r) ** yr for amt, yr in zip(amounts, years))

    def _dnpv(r: float) -> float:
        return -sum(
            yr * amt / ((1 + r) ** yr * (1 + r)) for amt, yr in zip(amounts, years)
        )

    for r0 in (0.1, -0.5, 0.5, -0.1, 2.0):
        r = r0
        for _ in range(200):
            f_val = _npv(r)
            if abs(f_val) < 1e-6:
                return r * 100 if -1 < r < 100 else None
            df_val = _dnpv(r)
            if abs(df_val) < 1e-12:
                break
            r = r - f_val / df_val
            if not (-1 < r < 100):
                break
        else:
            return r * 100 if -1 < r < 100 else None
    return None


# ── Price helpers ─────────────────────────────────────────────────────────────


def nearest_price(series: list[dict], target_date: str) -> Optional[float]:
    """Return the first close price with date >= target_date within 10 calendar days.

    Args:
        series: List of {"date": "YYYY-MM-DD", "close": float} sorted ascending.
        target_date: The date to find a price on or after.

    Returns:
        The close price, or None if no suitable price is found in the window.
    """
    deadline = (
        datetime.strptime(target_date, "%Y-%m-%d")
        + timedelta(days=_NEAREST_PRICE_WINDOW_DAYS)
    ).strftime("%Y-%m-%d")
    for entry in series:
        if entry["date"] >= target_date:
            if entry["date"] <= deadline:
                return entry["close"]
            break
    return None


# ── Scheme simulation ─────────────────────────────────────────────────────────


def simulate_scheme(
    scheme: dict,
    deposits: list,
    price_cache: dict[str, list[dict]],
    current_prices: dict[str, float],
    fx: dict[str, float],
    terminal_date: Optional[str] = None,
) -> tuple[Optional[float], int, float]:
    """Simulate investing all deposits per *scheme* and compute the XIRR.

    Args:
        scheme: {"id", "name", "allocations": [{"symbol", "pct"}], "cash_pct": int}
        deposits: IncomeModel rows sorted by date.
        price_cache: symbol → [{date, close}] sorted ascending.
        current_prices: symbol → price at terminal_date (or current price when live).
        fx: currency → CNY-based rate (e.g. {"USD": 7.2, "CNY": 1.0}).
        terminal_date: If set, treat this date as "today" and only include deposits
            on or before this date. Used for historical backfill.

    Returns:
        (xirr_pct, excluded_deposit_count, terminal_value_usd).
    """
    today = terminal_date or str(datetime.now(timezone.utc).date())
    relevant = [d for d in deposits if d["date"] <= today]
    shares: dict[str, float] = defaultdict(float)
    cash_balance = 0.0
    flows: list[tuple[str, float]] = []
    excluded = 0

    usd_rate = fx.get("USD", 7.2)  # CNY per USD

    for dep in sorted(relevant, key=lambda d: d["date"]):
        dep_fx = fx.get(dep["currency"], 1.0)
        amount_usd = dep["amount"] * dep_fx / usd_rate

        is_deposit = dep["category"] == "deposit"
        flows.append((dep["date"], -amount_usd if is_deposit else amount_usd))

        if is_deposit:
            any_missing = False
            for alloc in scheme.get("allocations", []):
                sym = alloc["symbol"]
                pct = (
                    alloc["pct"] / 100
                )  # fraction of total deposit (not of investable)
                sym_series = price_cache.get(sym, [])
                price = nearest_price(sym_series, dep["date"])
                # If deposit predates instrument launch, use first available price
                if price is None and sym_series and dep["date"] < sym_series[0]["date"]:
                    price = sym_series[0]["close"]
                if price and price > 0:
                    shares[sym] += amount_usd * pct / price
                else:
                    any_missing = True
                    cash_balance += amount_usd * pct
            cash_balance += amount_usd * scheme.get("cash_pct", 0) / 100
            if any_missing:
                excluded += 1
        else:
            # Withdrawal: reduce shares + cash proportionally
            total = (
                sum(shares[s] * current_prices.get(s, 0) for s in shares) + cash_balance
            )
            ratio = min(amount_usd / max(total, 0.01), 1.0)
            for s in list(shares):
                shares[s] *= 1 - ratio
            cash_balance *= 1 - ratio

    terminal = sum(shares[s] * current_prices.get(s, 0) for s in shares) + cash_balance
    if terminal > 0:
        flows.append((today, terminal))

    flows.sort(key=lambda x: x[0])
    return xirr(flows), excluded, terminal


# ── ID-integrity check ───────────────────────────────────────────────────────


def warn_orphaned_bench_ids() -> None:
    """Warn at startup if stored bench_ids are no longer in config benchmark_defaults.

    Default scheme IDs are stored verbatim in benchmark_results.bench_id.
    Renaming or removing an ID in config/app.json orphans all historical rows
    for that scheme.  This function detects that drift early.
    """
    from fin.database import SessionLocal
    from sqlalchemy import text

    config_ids = {d["id"] for d in _load_benchmark_defaults()}
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT DISTINCT bench_id FROM benchmark_results WHERE bench_id != :p"
            ),
            {"p": _PORTFOLIO_BENCH_ID},
        ).fetchall()
    finally:
        db.close()

    # Custom scheme IDs are numeric strings — skip them
    orphaned = [
        r[0] for r in rows if not r[0].lstrip("-").isdigit() and r[0] not in config_ids
    ]
    if orphaned:
        logger.warning(
            "benchmark_results references IDs absent from config benchmark_defaults: %s"
            " — historical rows are orphaned. Never rename a default scheme ID.",
            orphaned,
        )


# ── Dedup helper ─────────────────────────────────────────────────────────────


def has_recent_result(db: Session, account_id: int) -> bool:
    """Return True if a valid result was computed within the configured interval.

    Reads benchmark_recompute_interval_minutes from config/app.json (default 10).
    Returns False when:
    - No portfolio row with a non-NULL xirr exists within the interval
    - Any currently-active scheme is missing a result within the interval
    """
    try:
        cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        interval = int(cfg.get("benchmark_recompute_interval_minutes", 10))
    except Exception as exc:
        logger.warning("Failed to read benchmark_recompute_interval_minutes: %s", exc)
        interval = 10

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=interval)
    today = str(datetime.now(timezone.utc).date())

    portfolio_row = (
        db.query(BenchmarkResultModel)
        .filter(
            BenchmarkResultModel.account_id == account_id,
            BenchmarkResultModel.computed_date == today,
            BenchmarkResultModel.bench_id == _PORTFOLIO_BENCH_ID,
            BenchmarkResultModel.xirr.isnot(None),
            BenchmarkResultModel.computed_at >= cutoff,
        )
        .first()
    )
    if portfolio_row is None:
        return False

    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == MOCK_USER_ID)
        .first()
    )
    if account is None:
        return False

    active_ids = {s["id"] for s in _resolve_schemes(db, account)}
    if not active_ids:
        return True

    computed_ids = {
        row[0]
        for row in db.query(BenchmarkResultModel.bench_id).filter(
            BenchmarkResultModel.account_id == account_id,
            BenchmarkResultModel.computed_date == today,
            BenchmarkResultModel.computed_at >= cutoff,
        )
    }
    return active_ids.issubset(computed_ids)


def _serialize_income(rows) -> list[dict]:
    """Serialize IncomeModel ORM rows to plain dicts safe for threaded access."""
    return [
        {
            "date": r.date,
            "currency": r.currency,
            "amount": r.amount,
            "category": r.category,
        }
        for r in rows
    ]


def _build_holdings_positions(
    db: Session,
    account: AccountModel,
    fx: dict[str, float],
) -> dict[str, tuple[float, HoldingModel]]:
    """Return {code: (live_shares, holding)} for all non-zero positions.

    Applies post-snapshot transaction deltas, matching the frontend's computePositions.
    Used by both _compute_portfolio_xirr and _build_portfolio_scheme.
    """
    holdings_all = (
        db.query(HoldingModel)
        .filter(
            HoldingModel.user_id == MOCK_USER_ID, HoldingModel.account == account.name
        )
        .all()
    )
    best: dict[str, HoldingModel] = {}
    for h in holdings_all:
        if h.code not in best or (h.snapshot_name or "") > (
            best[h.code].snapshot_name or ""
        ):
            best[h.code] = h

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
    delta: dict[str, float] = defaultdict(float)

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

    return {
        code: (h.shares + delta.get(code, 0.0), h)
        for code, h in best.items()
        if h.shares + delta.get(code, 0.0) > 0
    }


# ── compute() helpers ────────────────────────────────────────────────────────


def _fetch_price_data(
    sym_list: list[str], earliest_date: str
) -> tuple[dict[str, list[dict]], dict[str, float]]:
    """Fetch historical and live prices for all symbols in parallel.

    Args:
        sym_list: Sorted list of symbols to fetch.
        earliest_date: Start date for historical fetch ("YYYY-MM-DD").

    Returns:
        (price_cache, current_prices) both keyed by symbol.
    """
    price_cache: dict[str, list[dict]] = {}
    current_prices: dict[str, float] = {}

    def _fetch_history(sym: str) -> tuple[str, list[dict]]:
        from fin.database import SessionLocal

        worker_db = SessionLocal()
        try:
            return sym, fetch_symbol(worker_db, sym, earliest_date)
        except Exception as exc:
            logger.warning("Price fetch failed for %s: %s", sym, exc)
            return sym, []
        finally:
            worker_db.close()

    def _fetch_live(sym: str) -> tuple[str, Optional[float]]:
        return sym, _fetch_current_price(sym)

    n = min(max(1, len(sym_list)), 8)
    with ThreadPoolExecutor(max_workers=n) as ex:
        hist_futs = {ex.submit(_fetch_history, s): s for s in sym_list}
        live_futs = {ex.submit(_fetch_live, s): s for s in sym_list}
        for f in as_completed(hist_futs):
            sym, series = f.result()
            price_cache[sym] = series
        for f in as_completed(live_futs):
            sym, live = f.result()
            if live:
                current_prices[sym] = live
            else:
                series = price_cache.get(sym, [])
                if series:
                    current_prices[sym] = series[-1]["close"]

    return price_cache, current_prices


def _simulate_schemes(
    schemes: list[dict],
    income_plain: list[dict],
    price_cache: dict[str, list[dict]],
    current_prices: dict[str, float],
    fx: dict[str, float],
) -> tuple[list[dict], int]:
    """Simulate all schemes in parallel and return (results, total_excluded).

    Args:
        schemes: List of scheme dicts with id, name, allocations, cash_pct.
        income_plain: Serialized income rows.
        price_cache: Historical price series per symbol.
        current_prices: Live price per symbol.
        fx: CNY-based FX rates.

    Returns:
        (scheme_results list, total excluded deposit count).
    """
    scheme_results = []
    total_excluded = 0

    with ThreadPoolExecutor(max_workers=min(max(1, len(schemes)), 8)) as executor:
        future_to_scheme = {
            executor.submit(
                simulate_scheme, s, income_plain, price_cache, current_prices, fx
            ): s
            for s in schemes
        }
        for future in as_completed(future_to_scheme):
            s = future_to_scheme[future]
            try:
                xirr_pct, excl, scheme_value_usd = future.result()
                total_excluded = max(total_excluded, excl)
            except Exception as exc:
                logger.warning("Scheme %s simulation failed: %s", s.get("id"), exc)
                xirr_pct = None
                scheme_value_usd = None
            scheme_results.append(
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "xirr": xirr_pct,
                    "current_value_usd": scheme_value_usd,
                }
            )

    return scheme_results, total_excluded


def _compute_portfolio_snap_results(
    db: Session,
    account_id: int,
    income_plain: list[dict],
    price_cache: dict[str, list[dict]],
    current_prices: dict[str, float],
    fx: dict[str, float],
) -> list[dict]:
    """Compute today's XIRR for all enabled portfolio composition snapshots.

    The backfill only runs to yesterday; this provides today's live data point
    for every enabled snapshot, not just the most recent one.
    Returns a list of scheme_result dicts (may be empty).
    """
    snaps = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account_id,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 1,
            BenchmarkCustomSchemeModel.enabled != 0,
        )
        .order_by(BenchmarkCustomSchemeModel.id)
        .all()
    )
    if not snaps:
        return []

    earliest = income_plain[0]["date"] if income_plain else None
    results = []
    for snap in snaps:
        snap_scheme = {
            "id": str(snap.id),
            "name": snap.name,
            "allocations": json.loads(snap.allocations_json),
            "cash_pct": snap.cash_pct,
        }
        for a in snap_scheme["allocations"]:
            sym = a["symbol"]
            if sym not in price_cache:
                try:
                    price_cache[sym] = (
                        fetch_symbol(db, sym, earliest) if earliest else []
                    )
                except Exception:
                    price_cache[sym] = []
            if sym not in current_prices:
                live = _fetch_current_price(sym)
                if live:
                    current_prices[sym] = live
                elif price_cache.get(sym):
                    current_prices[sym] = price_cache[sym][-1]["close"]

        try:
            snap_xirr, _, snap_value = simulate_scheme(
                snap_scheme, income_plain, price_cache, current_prices, fx
            )
            results.append(
                {
                    "id": str(snap.id),
                    "name": snap.name,
                    "xirr": snap_xirr,
                    "current_value_usd": snap_value,
                }
            )
        except Exception as exc:
            logger.warning("Portfolio snapshot compute failed for %s: %s", snap.id, exc)
    return results


def _write_bench_results(
    db: Session,
    account_id: int,
    today: str,
    portfolio_xirr: Optional[float],
    portfolio_value_usd: float,
    scheme_results: list[dict],
) -> None:
    """Upsert one BenchmarkResultModel row per bench_id."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    now_utc = datetime.now(timezone.utc)
    rows_to_write = [(_PORTFOLIO_BENCH_ID, portfolio_xirr, portfolio_value_usd)]
    for sr in scheme_results:
        rows_to_write.append((sr["id"], sr.get("xirr"), sr.get("current_value_usd")))

    for bench_id, xirr_val, value_usd in rows_to_write:
        stmt = sqlite_insert(BenchmarkResultModel).values(
            account_id=account_id,
            bench_id=bench_id,
            computed_date=today,
            xirr=xirr_val,
            current_value_usd=value_usd,
            computed_at=now_utc,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["account_id", "bench_id", "computed_date"],
            set_={
                "xirr": stmt.excluded.xirr,
                "current_value_usd": stmt.excluded.current_value_usd,
                "computed_at": stmt.excluded.computed_at,
            },
        )
        db.execute(stmt)
    db.commit()


# ── Main service ──────────────────────────────────────────────────────────────


def _load_benchmark_defaults() -> list[dict]:
    """Read benchmark_defaults from config/app.json (cached after first successful load)."""
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is not None:
        return _DEFAULTS_CACHE
    try:
        cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        _DEFAULTS_CACHE = cfg.get("benchmark_defaults", [])
        return _DEFAULTS_CACHE
    except Exception as exc:
        logger.warning("Failed to load benchmark_defaults: %s", exc)
        return []


def _resolve_schemes(db: Session, account: AccountModel) -> list[dict]:
    """Return the list of active schemes for *account*.

    Default schemes are filtered by enabled_defaults stored in account.benchmark_schemes.
    Custom schemes are loaded from the benchmark_custom_schemes table.
    """
    defaults = {d["id"]: d for d in _load_benchmark_defaults()}

    enabled_ids = list(defaults.keys())
    if account.benchmark_schemes:
        try:
            stored = json.loads(account.benchmark_schemes)
            enabled_ids = stored.get("enabled_defaults", list(defaults.keys()))
        except (json.JSONDecodeError, TypeError):
            pass

    active = [defaults[i] for i in enabled_ids if i in defaults]

    customs = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account.id,
            BenchmarkCustomSchemeModel.enabled != 0,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 0,
        )
        .order_by(BenchmarkCustomSchemeModel.id)
        .all()
    )
    for row in customs:
        active.append(
            {
                "id": str(row.id),
                "name": row.name,
                "allocations": json.loads(row.allocations_json),
                "cash_pct": row.cash_pct,
            }
        )

    return active


def _fetch_fx(db: Session) -> dict[str, float]:
    """Return CNY-based FX rates for common currencies."""
    try:
        from fin.services.quote import QuoteService
        from fin.services.providers import build_default_providers

        return QuoteService(db, build_default_providers()).get_fx(_FX_PAIRS)
    except Exception as exc:
        logger.warning("FX fetch failed, using fallbacks: %s", exc)
        return {"CNY": 1.0, "USD": 7.2, "HKD": 0.92, "CAD": 5.3}


def _fetch_current_price(symbol: str) -> Optional[float]:
    """Fetch current price via QuoteService (routes to EastMoney for OTC funds)."""
    from fin.database import SessionLocal
    from fin.services.providers import build_default_providers
    from fin.services.quote import QuoteService

    db = SessionLocal()
    try:
        q = QuoteService(db, build_default_providers()).get_quote(symbol)
        if q and q.get("price"):
            return float(q["price"])
        return None
    except Exception as exc:
        logger.debug("QuoteService price lookup failed for %s: %s", symbol, exc)
        return None
    finally:
        db.close()


def _holding_current_price(
    db: Session, code: str, fallback_series: list[dict]
) -> Optional[float]:
    """Return current price for a portfolio holding using the full provider chain.

    Tries the QuoteService (stocks cache → provider) so CN mutual funds
    (6-digit codes via EastMoney), HK stocks, and A-shares all resolve
    correctly. Falls back to the latest price_history entry, then bare
    yfinance (works for US symbols even without a cached row).

    Args:
        db: SQLAlchemy session.
        code: Raw holding code as stored in HoldingModel (e.g. "013308",
              "00700", "000651.SZ", "NVDA").
        fallback_series: price_history entries for this code; used when
            QuoteService has no price.

    Returns:
        Float price, or None if all methods fail.
    """
    try:
        from fin.services.providers import build_default_providers
        from fin.services.quote import QuoteService

        q = QuoteService(db, build_default_providers()).get_quote(code)
        if q and q.get("price"):
            return float(q["price"])
    except Exception as exc:
        logger.debug("QuoteService price lookup failed for holding %s: %s", code, exc)
    if fallback_series:
        return fallback_series[-1]["close"]
    return None


def compute(db: Session, account_id: int) -> dict:
    """Compute benchmark XIRR for all active schemes for *account_id*.

    Writes one BenchmarkResultModel row per bench_id (including __portfolio__).
    Always recomputes — callers handle same-day caching.

    Args:
        db: Active SQLAlchemy session.
        account_id: Primary key of the account.

    Returns:
        Dict with keys: portfolio_xirr, schemes, computed_date, excluded_deposits.

    Raises:
        ValueError: If the account does not exist or benchmark is disabled.
    """
    today = str(datetime.now(timezone.utc).date())

    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == MOCK_USER_ID)
        .first()
    )
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    if account.benchmark_enabled != "1":
        raise ValueError(f"Account {account_id} has benchmark disabled")

    schemes = _resolve_schemes(db, account)
    if not schemes:
        return {
            "portfolio_xirr": None,
            "schemes": [],
            "computed_date": today,
            "excluded_deposits": 0,
        }

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
        return {
            "portfolio_xirr": None,
            "schemes": [
                {"id": s.get("id"), "name": s.get("name"), "xirr": None}
                for s in schemes
            ],
            "computed_date": today,
            "excluded_deposits": 0,
        }

    earliest_date = income[0].date
    # Serialize before threading — SQLAlchemy ORM instances are not thread-safe.
    income_plain = _serialize_income(income)

    all_symbols: set[str] = {
        a["symbol"] for s in schemes for a in s.get("allocations", [])
    }
    price_cache, current_prices = _fetch_price_data(sorted(all_symbols), earliest_date)
    fx = _fetch_fx(db)

    portfolio_xirr, portfolio_value_usd = _compute_portfolio_xirr(
        db, account, income_plain, fx, price_cache, earliest_date
    )

    scheme_results, total_excluded = _simulate_schemes(
        schemes, income_plain, price_cache, current_prices, fx
    )
    scheme_order = {s.get("id"): i for i, s in enumerate(schemes)}
    scheme_results.sort(key=lambda r: scheme_order.get(r["id"], 999))

    snap_results = _compute_portfolio_snap_results(
        db, account_id, income_plain, price_cache, current_prices, fx
    )
    scheme_results.extend(snap_results)

    _write_bench_results(
        db, account_id, today, portfolio_xirr, portfolio_value_usd, scheme_results
    )

    return {
        "portfolio_xirr": portfolio_xirr,
        "portfolio_value_usd": portfolio_value_usd,
        "schemes": scheme_results,
        "computed_date": today,
        "excluded_deposits": total_excluded,
    }


def _compute_portfolio_xirr(
    db: Session,
    account: AccountModel,
    income: list,
    fx: dict[str, float],
    price_cache: dict[str, list[dict]],
    earliest_date: str,
) -> tuple[Optional[float], float]:
    """Compute XIRR for the actual portfolio using income flows + current holdings value.

    Uses the shared price_cache (populated during scheme computation) so holding
    prices come from the price_history table rather than fresh yfinance calls,
    which handles non-US symbols more reliably.

    Args:
        db: SQLAlchemy session.
        account: Account model.
        income: Income records (deposit/withdrawal) sorted by date.
        fx: CNY-based FX rates.
        price_cache: Mutable cache of {symbol: [{date, close}]} shared with scheme
            computation. New symbols are fetched and added here in place.
        earliest_date: Earliest income date — used as the since parameter when
            fetching price history for new symbols.

    Returns:
        XIRR as percentage, or None if not computable.
    """
    usd_rate = fx.get("USD", 7.2)
    flows: list[tuple[str, float]] = []

    for dep in income:
        dep_fx = fx.get(dep["currency"], 1.0)
        amount_usd = dep["amount"] * dep_fx / usd_rate
        if dep["category"] == "deposit":
            flows.append((dep["date"], -amount_usd))
        else:
            flows.append((dep["date"], amount_usd))

    positions = _build_holdings_positions(db, account, fx)
    terminal_usd = 0.0
    for code, (live_shares, h) in positions.items():
        if code == "CASH":
            price = 1.0
        else:
            if code not in price_cache:
                try:
                    price_cache[code] = fetch_symbol(db, code, earliest_date)
                except Exception as exc:
                    logger.warning("Price fetch failed for holding %s: %s", code, exc)
                    price_cache[code] = []
            series = price_cache.get(code, [])
            price = _holding_current_price(db, code, series)
        if price is None:
            continue
        terminal_usd += live_shares * price * fx.get(h.currency, 1.0) / usd_rate

    if terminal_usd > 0:
        today = str(datetime.now(timezone.utc).date())
        flows.append((today, terminal_usd))

    flows.sort(key=lambda x: x[0])
    return xirr(flows), terminal_usd
