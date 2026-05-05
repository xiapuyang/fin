import re
from abc import ABC, abstractmethod

# Matches 6-digit all-numeric codes (open-end funds and bare ETF codes).
# Defined here so both ChinaFundProvider and YFinanceProvider share one source.
_CN_FUND_PATTERN = re.compile(r"^\d{6}$")


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
    def fetch_live(self, symbol: str) -> dict:
        """Fetch a lightweight price snapshot.

        Returns a dict with at least: price, prev_close. May include
        open_price, high, low, currency, market_state. Returns {} on failure.
        """
        ...

    @abstractmethod
    def fetch_full(self, symbol: str) -> dict:
        """Fetch a comprehensive quote including fundamentals.

        Returns a dict compatible with StockModel fields. Returns {} on failure.
        """
        ...

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
