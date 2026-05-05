import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from fin.config import MARKET_STATE_PATH
from fin.models.stock import StockModel
from fin.repositories.stock_sqlite import StockSQLiteRepository

logger = logging.getLogger(__name__)

STALE_SECONDS = 300

SYMBOL_ALIASES = {".SPX": "^GSPC", ".NDX": "^NDX", ".DJI": "^DJI"}

_EXCHANGE_SUFFIXES = (".HK", ".SS", ".SZ")

_SUFFIX_TO_MARKET = {".HK": "HK", ".SS": "CN", ".SZ": "CN"}


def _market_for_symbol(symbol: str) -> str:
    for suffix, market in _SUFFIX_TO_MARKET.items():
        if symbol.endswith(suffix):
            return market
    return "US"


def _read_market_states() -> dict:
    try:
        return json.loads(MARKET_STATE_PATH.read_text())
    except Exception:
        return {}


def _write_market_state(symbol: str, state: str) -> None:
    market = _market_for_symbol(symbol)
    states = _read_market_states()
    states[market] = state
    try:
        MARKET_STATE_PATH.write_text(json.dumps(states))
    except Exception as e:
        logger.warning("failed to write market state: %s", e)


def normalize_symbol(symbol: str) -> str:
    s = symbol.upper()
    return SYMBOL_ALIASES.get(s, s)


def _dot_to_dash(symbol: str) -> str | None:
    """Return a dot-to-dash variant for US class-share tickers (BRK.B → BRK-B).

    Returns None for exchange-suffixed symbols (.HK, .SS, .SZ) or symbols
    without a dot.
    """
    if "." not in symbol:
        return None
    if any(symbol.endswith(s) for s in _EXCHANGE_SUFFIXES):
        return None
    return symbol.replace(".", "-")


def _fetch_live(symbol: str) -> dict:
    try:
        import yfinance as yf

        fi = yf.Ticker(symbol).fast_info
        price = fi.last_price
        # regular_market_previous_close is always the most recent completed
        # trading session's close; fi.previous_close can lag by one session
        # during pre-market hours, producing a stale change_pct.
        prev_close = (
            getattr(fi, "regular_market_previous_close", None) or fi.previous_close
        )
        if not price or not prev_close or prev_close == 0:
            return {}
        return {
            "price": price,
            "prev_close": prev_close,
            "open_price": getattr(fi, "open", None),
            "high": getattr(fi, "day_high", None),
            "low": getattr(fi, "day_low", None),
            "currency": getattr(fi, "currency", "USD") or "USD",
            "market_state": getattr(fi, "market_state", None),
        }
    except Exception as e:
        logger.warning("live fetch failed for %s: %s", symbol, e)
        return {}


def fetch_full_quote(symbol: str) -> dict:
    """Fetch comprehensive quote via yfinance .info (used by background updater)."""
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
        if not price or not prev_close or prev_close == 0:
            return {}
        volume = info.get("regularMarketVolume") or info.get("volume")
        float_shares = info.get("floatShares")
        dividend_yield = info.get("dividendYield")
        return {
            "name": info.get("shortName") or info.get("longName"),
            "currency": info.get("currency", "USD"),
            "price": price,
            "prev_close": prev_close,
            "open_price": info.get("regularMarketOpen") or info.get("open"),
            "high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
            "low": info.get("dayLow") or info.get("regularMarketDayLow"),
            "volume": volume,
            "amount": (volume * price) if volume else None,
            "turnover_rate": (volume / float_shares * 100)
            if volume and float_shares
            else None,
            "pe_ttm": info.get("trailingPE"),
            "pe_dynamic": info.get("forwardPE"),
            "pb": info.get("priceToBook"),
            "market_cap": info.get("marketCap"),
            "total_shares": info.get("sharesOutstanding"),
            "float_shares": float_shares,
            "float_market_cap": (float_shares * price) if float_shares else None,
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "beta": info.get("beta"),
            "dividend_ttm": info.get("dividendRate"),
            "dividend_rate": (dividend_yield * 100) if dividend_yield else None,
        }
    except Exception as e:
        logger.warning("full quote fetch failed for %s: %s", symbol, e)
        return {}


def _stock_to_dict(stock: StockModel) -> dict:
    change_pct = None
    if stock.price and stock.prev_close and stock.prev_close != 0:
        change_pct = (stock.price - stock.prev_close) / stock.prev_close * 100
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "price": stock.price,
        "prev_close": stock.prev_close,
        "change_pct": change_pct,
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
        "updated_at": stock.updated_at.isoformat(),
    }


class QuoteService:
    def __init__(self, db: Session) -> None:
        self._repo = StockSQLiteRepository(db)

    def get_quote(self, symbol: str) -> dict | None:
        symbol = normalize_symbol(symbol)
        stock = self._repo.get_by_symbol(symbol)

        if stock and stock.price and self._is_fresh(stock.updated_at):
            result = _stock_to_dict(stock)
            states = _read_market_states()
            result["market_state"] = states.get(_market_for_symbol(symbol))
            return result

        data = _fetch_live(symbol)
        if not data:
            alt = _dot_to_dash(symbol)
            if alt:
                data = _fetch_live(alt)
                if data:
                    symbol = alt

        if data:
            if data.get("market_state"):
                _write_market_state(symbol, data["market_state"])
            safe = {
                k: v for k, v in data.items() if k not in ("market_state", "change_pct")
            }
            self._repo.upsert(symbol, safe)
            stock = self._repo.get_by_symbol(symbol)
            result = _stock_to_dict(stock)
            result["market_state"] = data.get("market_state")
            return result

        if stock and stock.price:
            return _stock_to_dict(stock)

        return None

    @staticmethod
    def _is_fresh(updated_at: datetime) -> bool:
        now = datetime.utcnow()
        return (now - updated_at).total_seconds() < STALE_SECONDS
