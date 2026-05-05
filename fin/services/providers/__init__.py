import threading

from fin.services.providers.base import QuoteProvider

__all__ = ["QuoteProvider", "build_default_providers"]

_default_providers: list[QuoteProvider] | None = None
_providers_lock = threading.Lock()


def build_default_providers() -> list[QuoteProvider]:
    """Return the shared default provider list (constructed once per process).

    ChinaFundProvider comes first: it matches a strict subset (6-digit numeric
    codes). YFinanceProvider is the catch-all for everything else.

    The singleton ensures YFinanceProvider._fx_cache survives across requests.
    """
    global _default_providers
    if _default_providers is None:
        with _providers_lock:
            if _default_providers is None:
                from fin.services.providers.china_fund_provider import ChinaFundProvider
                from fin.services.providers.yfinance_provider import YFinanceProvider

                _default_providers = [ChinaFundProvider(), YFinanceProvider()]
    return _default_providers
