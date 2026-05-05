import logging
import time

import yfinance as yf

from fin.services.providers.base import CN_FUND_PATTERN, QuoteProvider

logger = logging.getLogger(__name__)

_EXCHANGE_SUFFIXES = (".HK", ".SS", ".SZ")

_FX_TTL = 60  # seconds

_ASSET_TYPES = frozenset({"equity", "etf", "bond", "mutualfund", "index"})


class YFinanceProvider(QuoteProvider):
    """Data provider backed by yfinance (Yahoo Finance).

    Handles US, HK, and Chinese exchange-listed ETFs (.SS/.SZ).
    Does NOT handle 6-digit open-end fund codes — those belong to ChinaFundProvider.
    """

    def __init__(self) -> None:
        self._fx_cache: dict[str, tuple[float, float]] = {}

    def supports(self, symbol: str) -> bool:
        """Return True for any symbol that is not a 6-digit all-numeric CN fund code."""
        return not CN_FUND_PATTERN.match(symbol)

    def fetch_live(self, symbol: str) -> dict:
        """Fetch price snapshot via yfinance fast_info.

        Includes BRK.B-style dot-to-dash retry internally.
        """
        data = self._fetch_live_raw(symbol)
        if not data:
            alt = self._dot_to_dash(symbol)
            if alt:
                data = self._fetch_live_raw(alt)
        return data

    def _fetch_live_raw(self, symbol: str) -> dict:
        try:
            fi = yf.Ticker(symbol).fast_info
            price = fi.last_price
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

    def fetch_full(self, symbol: str) -> dict:
        """Fetch comprehensive quote via yfinance .info."""
        try:
            info = yf.Ticker(symbol).info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            prev_close = info.get("regularMarketPreviousClose") or info.get(
                "previousClose"
            )
            if not price or not prev_close or prev_close == 0:
                return {}
            volume = info.get("regularMarketVolume") or info.get("volume")
            float_shares = info.get("floatShares")
            dividend_yield = info.get("dividendYield")
            category = info.get("category") or ""
            quote_type = (info.get("quoteType") or "equity").lower()
            if "bond" in category.lower():
                asset_type = "bond"
            elif quote_type in _ASSET_TYPES:
                asset_type = quote_type
            else:
                asset_type = "equity"

            return {
                "name": info.get("shortName") or info.get("longName"),
                "currency": info.get("currency", "USD"),
                "asset_type": asset_type,
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

    def fetch_fx(self, pairs: dict[str, str]) -> dict:
        """Fetch CNY-based FX rates with a 60s in-memory cache.

        Args:
            pairs: Mapping of currency code → Yahoo Finance ticker,
                   e.g. {"USD": "USDCNY=X"}.

        Returns:
            Dict of currency code → float rate. Falls back to the cached
            value if the live fetch fails; CNY is always 1.0.
        """
        rates: dict[str, float] = {"CNY": 1.0}
        now = time.monotonic()
        for ccy, ticker in pairs.items():
            cached_rate, cached_at = self._fx_cache.get(ccy, (None, 0.0))
            if cached_rate is not None and (now - cached_at) < _FX_TTL:
                rates[ccy] = cached_rate
                continue
            try:
                info = yf.Ticker(ticker).fast_info
                price = getattr(info, "last_price", None) or getattr(
                    info, "regularMarketPrice", None
                )
                if price and price > 0:
                    rate = round(float(price), 4)
                    rates[ccy] = rate
                    self._fx_cache[ccy] = (rate, now)
                elif cached_rate is not None:
                    rates[ccy] = cached_rate
            except Exception:
                if cached_rate is not None:
                    rates[ccy] = cached_rate
        return rates

    @staticmethod
    def _dot_to_dash(symbol: str) -> str | None:
        if "." not in symbol:
            return None
        if any(symbol.endswith(s) for s in _EXCHANGE_SUFFIXES):
            return None
        return symbol.replace(".", "-")
