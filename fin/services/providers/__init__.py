from fin.services.providers.base import QuoteProvider

__all__ = ["QuoteProvider", "build_default_providers"]


def build_default_providers() -> list[QuoteProvider]:
    """Return the default ordered provider list used by all entry points.

    ChinaFundProvider comes first: it matches a strict subset (6-digit numeric
    codes). YFinanceProvider is the catch-all for everything else.
    """
    from fin.services.providers.china_fund_provider import ChinaFundProvider
    from fin.services.providers.yfinance_provider import YFinanceProvider

    return [ChinaFundProvider(), YFinanceProvider()]
