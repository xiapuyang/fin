import concurrent.futures
import json
import logging
import math
import re
import urllib.request

from fin.services.providers.base import CN_FUND_PATTERN, QuoteProvider

logger = logging.getLogger(__name__)

# EastMoney JSONP endpoint returns intraday estimated NAV + last confirmed NAV.
_EASTMONEY_URL = "https://fundgz.1234567.com.cn/js/{code}.js"


class ChinaFundProvider(QuoteProvider):
    """Data provider for 6-digit Chinese fund codes.

    Handles open-end mutual funds (013308-style) that Yahoo Finance cannot serve.
    Also matches bare ETF codes without exchange suffix (e.g. "510310") — the
    YFinanceProvider handles the suffixed form "510310.SS".

    fetch_live: EastMoney JSONP endpoint for real-time estimated NAV.
    fetch_full: akshare fund_open_fund_info_em for historical NAV series.
    """

    def supports(self, symbol: str) -> bool:
        """Return True if symbol is a 6-digit all-numeric CN fund code."""
        return bool(CN_FUND_PATTERN.match(symbol))

    def fetch_live(self, symbol: str) -> dict:
        """Fetch real-time estimated NAV from EastMoney.

        Returns price (today's estimated NAV gsz), prev_close (last confirmed
        NAV dwjz), currency "CNY", and market_state=None.
        Returns {} on any failure.
        """
        url = _EASTMONEY_URL.format(code=symbol)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                # JSONP payload is always <500 bytes; cap read to avoid slow-drip stalls.
                text = resp.read(4096).decode("utf-8")

            match = re.search(r"jsonpgz\((.+)\)", text, re.DOTALL)
            if not match:
                logger.warning(
                    "unexpected EastMoney response for %s: %s", symbol, text[:120]
                )
                return {}

            data = json.loads(match.group(1))
            gsz = data.get("gsz")
            dwjz = data.get("dwjz")

            if not gsz or not dwjz:
                logger.warning("missing NAV fields for %s: %s", symbol, data)
                return {}

            price = float(gsz)
            prev_close = float(dwjz)

            if not math.isfinite(price) or not math.isfinite(prev_close):
                logger.warning(
                    "non-finite NAV for %s: gsz=%s dwjz=%s", symbol, gsz, dwjz
                )
                return {}

            if price <= 0 or prev_close <= 0:
                return {}

            return {
                "price": price,
                "prev_close": prev_close,
                "currency": "CNY",
                "market_state": None,
                "name": data.get("name"),
            }
        except Exception as e:
            logger.warning("EastMoney fetch failed for %s: %s", symbol, e)
            return {}

    def fetch_full(self, symbol: str) -> dict:
        """Fetch historical NAV series via akshare and return the latest entry.

        Returns {} on failure. Fields not available for open-end funds
        (pe_ttm, market_cap, etc.) are omitted.
        """
        try:
            import akshare as ak
        except ImportError:
            logger.error(
                "akshare is not installed; cannot fetch full quote for %s", symbol
            )
            return {}

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(
                    ak.fund_open_fund_info_em, symbol=symbol, indicator="单位净值走势"
                )
                df = future.result(timeout=30)

            if df is None or df.empty:
                logger.warning("no NAV data from akshare for %s", symbol)
                return {}

            # DataFrame columns: nav_date, unit_nav, cumulative_nav, daily_return_rate
            latest = df.iloc[-1]
            prev_row = df.iloc[-2] if len(df) > 1 else latest

            nav_col = "单位净值"
            price = float(latest[nav_col])
            prev_close = float(prev_row[nav_col])

            if price <= 0:
                return {}

            return {
                "price": price,
                "prev_close": prev_close,
                "currency": "CNY",
                "asset_type": "mutualfund",
                "market_state": None,
            }
        except concurrent.futures.TimeoutError:
            logger.warning("akshare fetch_full timed out for %s", symbol)
            return {}
        except Exception as e:
            logger.warning("akshare fetch_full failed for %s: %s", symbol, e)
            return {}
