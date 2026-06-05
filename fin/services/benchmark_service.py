import hashlib
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

import yfinance as yf
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
_FX_PAIRS = {"USD": "USDCNY=X", "HKD": "HKDCNY=X", "CAD": "CADCNY=X"}
_PORTFOLIO_BENCH_ID = "__portfolio__"

# In-process cache: account_id → (config_fingerprint, computed_at_utc).
# Resets on server restart (acceptable — triggers one extra compute).
_compute_cache: dict[int, tuple[str, datetime]] = {}


# ── XIRR (Newton-Raphson) ─────────────────────────────────────────────────────


def xirr(flows: list[tuple]) -> Optional[float]:
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

    r = 0.1
    for _ in range(200):
        f_val = 0.0
        df_val = 0.0
        for i, amt in enumerate(amounts):
            pv = (1 + r) ** years[i]
            f_val += amt / pv
            df_val -= years[i] * amt / (pv * (1 + r))
        if abs(f_val) < 1e-6:
            break
        if abs(df_val) < 1e-12:
            break
        r = r - f_val / df_val
        if not (-1 < r < 100):
            return None
    return r * 100 if -1 < r < 100 else None


# ── Price helpers ─────────────────────────────────────────────────────────────


def nearest_price(series: list[dict], target_date: str) -> Optional[float]:
    """Return the first close price with date >= target_date within 10 calendar days.

    Args:
        series: List of {"date": "YYYY-MM-DD", "close": float} sorted ascending.
        target_date: The date to find a price on or after.

    Returns:
        The close price, or None if no suitable price is found in the window.
    """
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    deadline = target + timedelta(days=_NEAREST_PRICE_WINDOW_DAYS)
    for entry in series:
        entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        if entry_date >= target:
            if entry_date <= deadline:
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


def _config_fingerprint(schemes: list[dict]) -> str:
    """Return an MD5 hash of the active scheme configuration.

    Stable across re-orders: schemes and their allocations are sorted before hashing.
    """
    canonical = sorted(
        [
            {
                "id": s["id"],
                "cash_pct": round(s.get("cash_pct", 0.0), 4),
                "allocations": sorted(
                    [
                        {"symbol": a["symbol"], "pct": round(a["pct"], 4)}
                        for a in s.get("allocations", [])
                    ],
                    key=lambda a: a["symbol"],
                ),
            }
            for s in schemes
        ],
        key=lambda s: s["id"],
    )
    return hashlib.md5(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def has_recent_result(db: Session, account_id: int) -> bool:
    """Return True if a valid result was computed recently with the current config.

    Uses the in-process _compute_cache so any config change (different enabled
    schemes or allocation weights) immediately invalidates the cache, even within
    the interval window. interval is read from benchmark_recompute_interval_minutes
    in config/app.json (default 10 minutes).
    """
    try:
        cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        interval = int(cfg.get("benchmark_recompute_interval_minutes", 10))
    except Exception:
        interval = 10

    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == MOCK_USER_ID)
        .first()
    )
    if account is None:
        return False

    schemes = _resolve_schemes(db, account)
    if not schemes:
        return False

    current_fp = _config_fingerprint(schemes)
    cached = _compute_cache.get(account_id)
    if cached is None:
        return False

    cached_fp, cached_ts = cached
    if cached_fp != current_fp:
        return False

    elapsed = (datetime.now(timezone.utc) - cached_ts).total_seconds()
    return elapsed < interval * 60


# ── Main service ──────────────────────────────────────────────────────────────


def _load_benchmark_defaults() -> list[dict]:
    """Read benchmark_defaults from config/app.json."""
    try:
        cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("benchmark_defaults", [])
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
    """Fetch the current close price for *symbol* via yfinance."""
    try:
        hist = yf.Ticker(symbol).history(period="2d")
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        return float(closes.iloc[-1])
    except Exception:
        return None


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
    return _fetch_current_price(code)


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
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

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

    # Serialize ORM objects to plain dicts before any threaded or async access.
    # SQLAlchemy ORM instances are not thread-safe; passing them into a
    # ThreadPoolExecutor causes intermittent "Instance has been deleted" errors.
    income_plain = [
        {
            "date": r.date,
            "currency": r.currency,
            "amount": r.amount,
            "category": r.category,
        }
        for r in income
    ]

    all_symbols: set[str] = set()
    for scheme in schemes:
        for alloc in scheme.get("allocations", []):
            all_symbols.add(alloc["symbol"])

    # Fetch historical price series and live prices in parallel across symbols.
    price_cache: dict[str, list[dict]] = {}
    current_prices: dict[str, float] = {}
    sym_list = sorted(all_symbols)

    def _fetch_history(sym: str) -> tuple[str, list[dict]]:
        try:
            return sym, fetch_symbol(db, sym, earliest_date)
        except Exception as exc:
            logger.warning("Price fetch failed for %s: %s", sym, exc)
            return sym, []

    def _fetch_live(sym: str) -> tuple[str, Optional[float]]:
        return sym, _fetch_current_price(sym)

    n = max(1, len(sym_list))
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

    fx = _fetch_fx(db)

    portfolio_xirr, portfolio_value_usd = _compute_portfolio_xirr(
        db, account, income_plain, fx, price_cache, earliest_date
    )

    scheme_results = []
    total_excluded = 0

    with ThreadPoolExecutor(max_workers=max(1, len(schemes))) as executor:
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

    scheme_order = {s.get("id"): i for i, s in enumerate(schemes)}
    scheme_results.sort(key=lambda r: scheme_order.get(r["id"], 999))

    # Also compute today's result for the most recent portfolio snapshot so the
    # trend chart's last data point uses today's live prices (backfill only runs
    # to yesterday).
    latest_snap = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account_id,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 1,
        )
        .order_by(BenchmarkCustomSchemeModel.id.desc())
        .first()
    )
    if latest_snap:
        snap_scheme = {
            "id": str(latest_snap.id),
            "name": latest_snap.name,
            "allocations": json.loads(latest_snap.allocations_json),
            "cash_pct": latest_snap.cash_pct,
        }
        for a in snap_scheme["allocations"]:
            sym = a["symbol"]
            if sym not in price_cache:
                try:
                    price_cache[sym] = fetch_symbol(db, sym, earliest_date)
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
            scheme_results.append(
                {
                    "id": str(latest_snap.id),
                    "name": latest_snap.name,
                    "xirr": snap_xirr,
                    "current_value_usd": snap_value,
                }
            )
        except Exception as exc:
            logger.warning(
                "Portfolio snapshot compute failed for %s: %s", latest_snap.id, exc
            )

    # Write one row per bench_id (portfolio + each scheme)
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

    _compute_cache[account_id] = (_config_fingerprint(schemes), now_utc)

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
) -> Optional[float]:
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

    holdings_all = (
        db.query(HoldingModel)
        .filter(
            HoldingModel.user_id == MOCK_USER_ID,
            HoldingModel.account == account.name,
        )
        .all()
    )
    # Keep latest snapshot per code (matches frontend snapshotHoldings logic)
    best: dict[str, HoldingModel] = {}
    for h in holdings_all:
        if h.code not in best or (h.snapshot_name or "") > (
            best[h.code].snapshot_name or ""
        ):
            best[h.code] = h

    # Apply post-snapshot transactions so share counts match the frontend's computePositions
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
    # share delta: code -> float (positive = net bought since snapshot)
    delta: dict[str, float] = defaultdict(float)
    # CASH delta is in CASH's native currency (same units as h.shares for CASH holding)
    cash_currency = (best["CASH"].currency if "CASH" in best else "USD") or "USD"
    cash_fx = fx.get(cash_currency, 1.0)
    # Only adjust CASH for transactions that occurred after the CASH snapshot date.
    # The CASH snapshot already reflects all flows up to that point.
    cash_snap_date = (best["CASH"].snapshot_name if "CASH" in best else "") or ""
    for t in transactions:
        if cutoff and t.date < cutoff:
            continue
        snap_date = (best[t.code].snapshot_name if t.code in best else "") or ""
        if t.date <= snap_date:
            continue
        if t.side == "buy":
            delta[t.code] += t.shares
        else:
            delta[t.code] -= t.shares
        # Deduct/credit CASH for post-snapshot stock trades (CASH snapshot is fixed)
        if t.code != "CASH" and "CASH" in best and t.date > cash_snap_date:
            cost_in_cash = t.shares * t.price * fx.get(t.currency, 1.0) / cash_fx
            if t.side == "buy":
                delta["CASH"] -= cost_in_cash
            else:
                delta["CASH"] += cost_in_cash

    terminal_usd = 0.0
    for code, h in best.items():
        live_shares = h.shares + delta.get(code, 0.0)
        if live_shares <= 0:
            continue
        # CASH is a virtual position where shares == amount in the holding currency
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
        h_fx = fx.get(h.currency, 1.0)
        terminal_usd += live_shares * price * h_fx / usd_rate

    if terminal_usd > 0:
        today = str(datetime.now(timezone.utc).date())
        flows.append((today, terminal_usd))

    flows.sort(key=lambda x: x[0])
    return xirr(flows), terminal_usd
