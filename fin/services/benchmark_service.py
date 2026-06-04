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
from fin.models.user import MOCK_USER_ID
from fin.services.price_history_service import fetch_symbol

logger = logging.getLogger(__name__)

_NEAREST_PRICE_WINDOW_DAYS = 10  # covers Chinese New Year holiday gap
_FX_PAIRS = {"USD": "USDCNY=X", "HKD": "HKDCNY=X", "CAD": "CADCNY=X"}
_PORTFOLIO_BENCH_ID = "__portfolio__"


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
) -> tuple[Optional[float], int]:
    """Simulate investing all deposits per *scheme* and compute the XIRR.

    Args:
        scheme: {"id", "name", "allocations": [{"symbol", "pct"}], "cash_pct": int}
        deposits: IncomeModel rows sorted by date.
        price_cache: symbol → [{date, close}] sorted ascending.
        current_prices: symbol → current close price.
        fx: currency → CNY-based rate (e.g. {"USD": 7.2, "CNY": 1.0}).

    Returns:
        (xirr_pct, excluded_deposit_count). xirr_pct is None on failure.
    """
    today = str(datetime.now(timezone.utc).date())
    shares: dict[str, float] = defaultdict(float)
    cash_balance = 0.0
    flows: list[tuple[str, float]] = []
    excluded = 0

    usd_rate = fx.get("USD", 7.2)  # CNY per USD

    for dep in sorted(deposits, key=lambda d: d["date"]):
        dep_fx = fx.get(dep["currency"], 1.0)
        amount_usd = dep["amount"] * dep_fx / usd_rate

        is_deposit = dep["category"] == "deposit"
        flows.append((dep["date"], -amount_usd if is_deposit else amount_usd))

        if is_deposit:
            investable = amount_usd * (1 - scheme.get("cash_pct", 0) / 100)
            any_missing = False
            for alloc in scheme.get("allocations", []):
                sym = alloc["symbol"]
                pct = alloc["pct"] / 100
                sym_series = price_cache.get(sym, [])
                price = nearest_price(sym_series, dep["date"])
                # If deposit predates instrument launch, use first available price
                if price is None and sym_series and dep["date"] < sym_series[0]["date"]:
                    price = sym_series[0]["close"]
                if price and price > 0:
                    shares[sym] += investable * pct / price
                else:
                    any_missing = True
                    cash_balance += investable * pct
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
    return xirr(flows), excluded


# ── Dedup helper ─────────────────────────────────────────────────────────────


def has_valid_result_today(db: Session, account_id: int) -> bool:
    """Return True if a non-NULL portfolio XIRR was already computed today.

    NULL xirr means computation failed or data was missing — treat as invalid
    so the next run retries.  An account with zero deposits will also get NULL,
    but re-running it is harmless (fast and idempotent).
    """
    today = str(datetime.now(timezone.utc).date())
    row = (
        db.query(BenchmarkResultModel)
        .filter(
            BenchmarkResultModel.account_id == account_id,
            BenchmarkResultModel.computed_date == today,
            BenchmarkResultModel.bench_id == _PORTFOLIO_BENCH_ID,
        )
        .first()
    )
    return row is not None and row.xirr is not None


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
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
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

    price_cache: dict[str, list[dict]] = {}
    for sym in sorted(all_symbols):
        try:
            price_cache[sym] = fetch_symbol(db, sym, earliest_date)
        except Exception as exc:
            logger.warning("Price fetch failed for %s: %s", sym, exc)
            price_cache[sym] = []

    current_prices: dict[str, float] = {}
    for sym in all_symbols:
        series = price_cache.get(sym, [])
        if series:
            current_prices[sym] = series[-1]["close"]
        else:
            price = _fetch_current_price(sym)
            if price:
                current_prices[sym] = price

    fx = _fetch_fx(db)

    portfolio_xirr = _compute_portfolio_xirr(
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
                xirr_pct, excl = future.result()
                total_excluded = max(total_excluded, excl)
            except Exception as exc:
                logger.warning("Scheme %s simulation failed: %s", s.get("id"), exc)
                xirr_pct = None
            scheme_results.append(
                {"id": s.get("id"), "name": s.get("name"), "xirr": xirr_pct}
            )

    scheme_order = {s.get("id"): i for i, s in enumerate(schemes)}
    scheme_results.sort(key=lambda r: scheme_order.get(r["id"], 999))

    # Write one row per bench_id (portfolio + each scheme)
    rows_to_write = [((_PORTFOLIO_BENCH_ID, portfolio_xirr))]
    for sr in scheme_results:
        rows_to_write.append((sr["id"], sr.get("xirr")))

    for bench_id, xirr_val in rows_to_write:
        stmt = sqlite_insert(BenchmarkResultModel).values(
            account_id=account_id,
            bench_id=bench_id,
            computed_date=today,
            xirr=xirr_val,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["account_id", "bench_id", "computed_date"],
            set_={"xirr": stmt.excluded.xirr},
        )
        db.execute(stmt)
    db.commit()

    return {
        "portfolio_xirr": portfolio_xirr,
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

    holdings = (
        db.query(HoldingModel)
        .filter(
            HoldingModel.user_id == MOCK_USER_ID,
            HoldingModel.account == account.name,
        )
        .all()
    )

    terminal_usd = 0.0
    for h in holdings:
        if h.shares <= 0:
            continue
        # CASH is a virtual position where shares == amount in the holding currency
        if h.code == "CASH":
            price = 1.0
        else:
            if h.code not in price_cache:
                try:
                    price_cache[h.code] = fetch_symbol(db, h.code, earliest_date)
                except Exception as exc:
                    logger.warning("Price fetch failed for holding %s: %s", h.code, exc)
                    price_cache[h.code] = []
            series = price_cache.get(h.code, [])
            price = series[-1]["close"] if series else _fetch_current_price(h.code)
        if price is None:
            continue
        h_fx = fx.get(h.currency, 1.0)
        value_usd = h.shares * price * h_fx / usd_rate
        terminal_usd += value_usd

    if terminal_usd > 0:
        today = str(datetime.now(timezone.utc).date())
        flows.append((today, terminal_usd))

    flows.sort(key=lambda x: x[0])
    return xirr(flows)
