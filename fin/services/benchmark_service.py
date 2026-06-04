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
from fin.models.benchmark_result import BenchmarkResultModel
from fin.models.holding import HoldingModel
from fin.models.income import IncomeModel
from fin.models.user import MOCK_USER_ID
from fin.services.price_history_service import fetch_symbol

logger = logging.getLogger(__name__)

_NEAREST_PRICE_WINDOW_DAYS = 10  # covers Chinese New Year holiday gap
_FX_PAIRS = {"USD": "USDCNY=X", "HKD": "HKDCNY=X", "CAD": "CADCNY=X"}


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

    for dep in sorted(deposits, key=lambda d: d.date):
        dep_fx = fx.get(dep.currency, 1.0)
        amount_usd = dep.amount * dep_fx / usd_rate

        is_deposit = dep.category == "deposit"
        flows.append((dep.date, -amount_usd if is_deposit else amount_usd))

        if is_deposit:
            investable = amount_usd * (1 - scheme.get("cash_pct", 0) / 100)
            any_missing = False
            for alloc in scheme.get("allocations", []):
                sym = alloc["symbol"]
                pct = alloc["pct"] / 100
                price = nearest_price(price_cache.get(sym, []), dep.date)
                if price and price > 0:
                    shares[sym] += investable * pct / price
                else:
                    any_missing = True
                    # Uninvested portion falls into cash
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


# ── Main service ──────────────────────────────────────────────────────────────


def _load_benchmark_defaults() -> list[dict]:
    """Read benchmark_defaults from config/app.json."""
    try:
        cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("benchmark_defaults", [])
    except Exception as exc:
        logger.warning("Failed to load benchmark_defaults: %s", exc)
        return []


def _resolve_schemes(account: AccountModel) -> list[dict]:
    """Return the list of active schemes for *account*.

    When benchmark_schemes is null, all defaults are active.
    """
    defaults = {d["id"]: d for d in _load_benchmark_defaults()}

    if not account.benchmark_schemes:
        return list(defaults.values())

    try:
        stored = json.loads(account.benchmark_schemes)
    except (json.JSONDecodeError, TypeError):
        return list(defaults.values())

    enabled_ids = stored.get("enabled_defaults", list(defaults.keys()))
    active = [defaults[i] for i in enabled_ids if i in defaults]
    active.extend(stored.get("custom_schemes", []))
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

    Writes results to benchmark_results (upserts today's row). Returns the
    same shape as GET /api/benchmark/results/{id}.

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

    schemes = _resolve_schemes(account)
    if not schemes:
        return {
            "portfolio_xirr": None,
            "schemes": [],
            "computed_date": today,
            "excluded_deposits": 0,
        }

    # Load income (deposit/withdrawal) for this account
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

    # Collect symbols from all schemes
    all_symbols: set[str] = set()
    for scheme in schemes:
        for alloc in scheme.get("allocations", []):
            all_symbols.add(alloc["symbol"])

    # Fetch price history sequentially (avoid yfinance rate limits)
    price_cache: dict[str, list[dict]] = {}
    for sym in sorted(all_symbols):
        try:
            price_cache[sym] = fetch_symbol(db, sym, earliest_date)
        except Exception as exc:
            logger.warning("Price fetch failed for %s: %s", sym, exc)
            price_cache[sym] = []

    # Current prices: latest close from price_history or live yfinance
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

    # Portfolio XIRR: all income flows + current holdings value
    portfolio_xirr = _compute_portfolio_xirr(db, account, income, fx)

    # Scheme XIRRs via ThreadPoolExecutor
    scheme_results = []
    total_excluded = 0

    with ThreadPoolExecutor(max_workers=max(1, len(schemes))) as executor:
        future_to_scheme = {
            executor.submit(
                simulate_scheme, s, income, price_cache, current_prices, fx
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

    # Preserve original scheme order
    scheme_order = {s.get("id"): i for i, s in enumerate(schemes)}
    scheme_results.sort(key=lambda r: scheme_order.get(r["id"], 999))

    # Upsert benchmark_results
    stmt = sqlite_insert(BenchmarkResultModel).values(
        account_id=account_id,
        computed_date=today,
        portfolio_xirr=portfolio_xirr,
        results_json=json.dumps(scheme_results),
        excluded_deposits=total_excluded,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "computed_date"],
        set_={
            "portfolio_xirr": stmt.excluded.portfolio_xirr,
            "results_json": stmt.excluded.results_json,
            "excluded_deposits": stmt.excluded.excluded_deposits,
        },
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
) -> Optional[float]:
    """Compute XIRR for the actual portfolio using income flows + current holdings value.

    Args:
        db: SQLAlchemy session.
        account: Account model.
        income: Income records (deposit/withdrawal) sorted by date.
        fx: CNY-based FX rates.

    Returns:
        XIRR as percentage, or None if not computable.
    """
    usd_rate = fx.get("USD", 7.2)
    flows: list[tuple[str, float]] = []

    for dep in income:
        dep_fx = fx.get(dep.currency, 1.0)
        amount_usd = dep.amount * dep_fx / usd_rate
        if dep.category == "deposit":
            flows.append((dep.date, -amount_usd))
        else:
            flows.append((dep.date, amount_usd))

    # Terminal value: current holdings for this account
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
        price = _fetch_current_price(h.code)
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
