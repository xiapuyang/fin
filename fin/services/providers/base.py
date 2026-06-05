import re
from abc import ABC, abstractmethod
from typing import Any

# Matches 6-digit all-numeric codes (open-end funds and bare ETF codes).
# Defined here so both ChinaFundProvider and YFinanceProvider share one source.
CN_FUND_PATTERN = re.compile(r"^\d{6}$")


class QuoteProvider(ABC):
    """Interface for fetching market data from a single data source.

    Implementations receive already-normalized symbols (e.g. "AAPL", "510310.SS").
    Caching, retry, and DB persistence are the responsibility of the caller.
    """

    @abstractmethod
    def supports(self, symbol: str) -> bool:
        """Return True if this provider can fetch data for the given symbol."""
        ...

    @abstractmethod
    def fetch_live(self, symbol: str) -> dict[str, Any]:
        """Fetch a lightweight price snapshot.

        Returns a dict with at least: price, prev_close. May include
        open_price, high, low, currency, market_state. Returns {} on failure.
        """
        ...

    @abstractmethod
    def fetch_full(self, symbol: str) -> dict[str, Any]:
        """Fetch a comprehensive quote including fundamentals.

        Returns a dict compatible with StockModel fields. Returns {} on failure.
        """
        ...

    def fetch_history(self, symbol: str, start: str, end: str) -> list[dict]:
        """Return OHLC history as [{"date": "YYYY-MM-DD", "close": float}] sorted ascending.

        Args:
            symbol: Normalized symbol.
            start: Start date inclusive "YYYY-MM-DD".
            end: End date exclusive "YYYY-MM-DD".

        Returns:
            List of {"date", "close"} dicts, or [] on failure or if unsupported.
        """
        return []

    def fetch_dividends(self, symbol: str, since: str) -> dict:
        """Return dividend metadata and payment history since since_date.

        Args:
            symbol: Normalized symbol.
            since: Earliest date to include "YYYY-MM-DD".

        Returns:
            {"ex_date": str|None, "pay_date": str|None, "annual_rate": float|None,
             "history": [{"date": str, "amount": float}]}
            or {} on failure or when dividends are not applicable for this symbol type.
        """
        return {}

    def fetch_fx(self, pairs: dict[str, str]) -> dict:
        """Fetch FX rates keyed by currency code.

        Args:
            pairs: Mapping of currency code to ticker symbol,
                   e.g. {"USD": "USDCNY=X"}.

        Returns:
            Dict of currency code → rate as float.

        Raises:
            NotImplementedError: If this provider does not support FX.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support FX fetching")
