import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from fin.config import MARKET_STATE_PATH
from fin.models.stock import StockModel
from fin.repositories.stock_sqlite import StockSQLiteRepository
from fin.services.providers.base import CN_FUND_PATTERN, QuoteProvider

logger = logging.getLogger(__name__)

STALE_SECONDS = 300

SYMBOL_ALIASES = {".SPX": "^GSPC", ".NDX": "^NDX", ".DJI": "^DJI"}

# Fields from provider responses that are not DB columns and must be stripped
# before persisting (market_state and change_pct are computed/transient).
_NON_DB_FIELDS = frozenset({"market_state", "change_pct", "after_hours_change_pct"})

_SUFFIX_TO_MARKET = {".HK": "HK", ".SS": "CN", ".SZ": "CN"}


def _market_for_symbol(symbol: str) -> str:
    # 6-digit CN fund codes have no exchange suffix; give them their own bucket
    # so they never inherit the US market state from market_state.json.
    if CN_FUND_PATTERN.match(symbol):
        return "CN_FUND"
    for suffix, market in _SUFFIX_TO_MARKET.items():
        if symbol.endswith(suffix):
            return market
    return "US"


def _read_market_states() -> dict:
    try:
        return json.loads(MARKET_STATE_PATH.read_text())
    except Exception:
        return {}


def normalize_symbol(symbol: str) -> str:
    s = symbol.upper()
    return SYMBOL_ALIASES.get(s, s)


def _stock_to_dict(stock: StockModel) -> dict:
    change_pct = None
    if stock.price and stock.prev_close and stock.prev_close != 0:
        change_pct = (stock.price - stock.prev_close) / stock.prev_close * 100
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "price": stock.price,
        "regular_close": stock.regular_close,
        "prev_close": stock.prev_close,
        "change_pct": change_pct,
        "after_hours_change_pct": (
            (stock.price - stock.regular_close) / stock.regular_close * 100
            if stock.price and stock.regular_close and stock.regular_close != 0
            else None
        ),
        "open_price": stock.open_price,
        "high": stock.high,
        "low": stock.low,
        "volume": stock.volume,
        "amount": stock.amount,
        "turnover_rate": stock.turnover_rate,
        "pe_ttm": stock.pe_ttm,
        "pe_dynamic": stock.pe_dynamic,
        "pb": stock.pb,
        "market_cap": stock.market_cap,
        "total_shares": stock.total_shares,
        "float_shares": stock.float_shares,
        "float_market_cap": stock.float_market_cap,
        "week_52_high": stock.week_52_high,
        "week_52_low": stock.week_52_low,
        "beta": stock.beta,
        "dividend_ttm": stock.dividend_ttm,
        "dividend_rate": stock.dividend_rate,
        "currency": stock.currency or "USD",
        "asset_type": stock.asset_type,
        "updated_at": stock.updated_at.isoformat(),
    }


class QuoteService:
    def __init__(self, db: Session, providers: list[QuoteProvider]) -> None:
        self._repo = StockSQLiteRepository(db)
        self._providers = providers

    def _select_provider(self, symbol: str) -> QuoteProvider:
        """Return the first provider that supports symbol, or raise ValueError."""
        for p in self._providers:
            if p.supports(symbol):
                return p
        raise ValueError(f"no provider supports symbol: {symbol!r}")

    def get_quote(self, symbol: str) -> dict | None:
        symbol = normalize_symbol(symbol)
        stock = self._repo.get_by_symbol(symbol)
        market_key = _market_for_symbol(symbol)

        if stock and stock.price and self._is_fresh(stock.updated_at):
            result = _stock_to_dict(stock)
            result["market_state"] = _read_market_states().get(market_key)
            return result

        try:
            provider = self._select_provider(symbol)
        except ValueError:
            return None
        data = provider.fetch_live(symbol)

        states = _read_market_states()
        if data:
            safe = {k: v for k, v in data.items() if k not in _NON_DB_FIELDS}
            if safe.get("regular_close") is None:
                safe.pop("regular_close", None)
            self._repo.upsert(symbol, safe)
            stock = self._repo.get_by_symbol(symbol)
            result = _stock_to_dict(stock)
            result["market_state"] = states.get(market_key)
            return result

        if stock and stock.price:
            result = _stock_to_dict(stock)
            result["market_state"] = states.get(market_key)
            return result

        return None

    def upsert_quote(self, symbol: str, data: dict) -> None:
        """Persist a quote data dict for symbol, ignoring non-DB fields."""
        safe = {k: v for k, v in data.items() if k not in _NON_DB_FIELDS}
        self._repo.upsert(symbol, safe)

    def get_full_quote(self, symbol: str) -> dict:
        """Fetch comprehensive quote via the appropriate provider.

        Returns {} when no provider supports the symbol (matches fetch_full
        contract on the base class).
        """
        symbol = normalize_symbol(symbol)
        try:
            provider = self._select_provider(symbol)
        except ValueError:
            return {}
        return provider.fetch_full(symbol)

    def get_fx(self, pairs: dict[str, str]) -> dict:
        """Fetch FX rates, delegating to the first provider that supports it.

        Raises:
            RuntimeError: If no provider implements FX fetching.
        """
        for provider in self._providers:
            try:
                return provider.fetch_fx(pairs)
            except NotImplementedError:
                continue
        raise RuntimeError("no provider supports FX fetching")

    @staticmethod
    def _is_fresh(updated_at: datetime) -> bool:
        now = datetime.utcnow()
        return (now - updated_at).total_seconds() < STALE_SECONDS
