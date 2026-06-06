"""Tests for YFinanceProvider."""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fin.services.providers.yfinance_provider import (
    YFinanceProvider,
    _CN_ETF_NAME_TTL,
    _cn_etf_name,
    _cn_etf_name_cache,
    _fetch_cn_etf_name,
)


@pytest.fixture()
def provider():
    return YFinanceProvider()


def _make_fast_info(price=150.0, prev_close=148.0, market_state="REGULAR"):
    fi = MagicMock()
    fi.last_price = price
    fi.previous_close = prev_close
    fi.regular_market_previous_close = prev_close
    fi.open = 149.0
    fi.day_high = 151.0
    fi.day_low = 147.0
    fi.currency = "USD"
    fi.market_state = market_state
    return fi


def _make_history(close=150.0, prev_close=148.0, today=True):
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)
    last = now if today else yesterday
    dates = [yesterday - timedelta(days=1) if not today else yesterday, last]
    return pd.DataFrame({"Close": [prev_close, close]}, index=pd.DatetimeIndex(dates))


# ── supports ─────────────────────────────────────────────────────────────────


def test_supports_regular_symbols(provider):
    assert provider.supports("AAPL") is True
    assert provider.supports("510310.SS") is True
    assert provider.supports("159892.SZ") is True
    assert provider.supports("^GSPC") is True
    assert provider.supports("BRK.B") is True


def test_supports_rejects_cn_fund_codes(provider):
    assert provider.supports("013308") is False
    assert provider.supports("510310") is False
    assert provider.supports("000001") is False


# ── fetch_live ────────────────────────────────────────────────────────────────


def test_fetch_live_returns_price_dict(provider):
    fi = _make_fast_info()
    hist = _make_history()
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_live("AAPL")

    assert result["price"] == 150.0
    assert result["prev_close"] == 148.0
    assert result["market_state"] == "REGULAR"
    assert "open_price" in result


def test_fetch_live_returns_empty_on_zero_price(provider):
    fi = _make_fast_info(price=0.0)
    hist = _make_history(close=0.0)
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_live("AAPL")
    assert result == {}


def test_fetch_live_returns_empty_when_close_is_nan(provider):
    # yfinance sometimes returns NaN close during PREPRE/CLOSED — must not be stored as NULL
    fi = _make_fast_info()
    hist = _make_history(close=float("nan"))
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_live("0700.HK")
    assert result == {}


def test_fetch_live_returns_empty_when_prev_close_is_nan(provider):
    fi = _make_fast_info()
    hist = _make_history(close=466.4, prev_close=float("nan"))
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_live("0700.HK")
    assert result == {}


def test_fetch_live_dot_to_dash_retry(provider):
    fi = _make_fast_info()
    hist = _make_history()
    call_count = {"n": 0}

    def make_ticker(sym):
        t = MagicMock()
        call_count["n"] += 1
        if sym == "BRK.B":
            t.fast_info = _make_fast_info(price=0.0)
            t.history.return_value = pd.DataFrame()  # empty → returns {}
        else:
            t.fast_info = fi
            t.history.return_value = hist
        return t

    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.side_effect = make_ticker
        result = provider.fetch_live("BRK.B")

    assert result["price"] == 150.0
    assert call_count["n"] == 2  # tried BRK.B then BRK-B


def test_fetch_live_returns_empty_on_exception(provider):
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.side_effect = Exception("network error")
        result = provider.fetch_live("AAPL")
    assert result == {}


# ── fetch_full ────────────────────────────────────────────────────────────────


def test_fetch_full_returns_fundamentals(provider):
    info = {
        "regularMarketPrice": 150.0,
        "regularMarketPreviousClose": 148.0,
        "shortName": "Apple Inc.",
        "currency": "USD",
        "quoteType": "EQUITY",
        "trailingPE": 28.5,
        "marketCap": 2_000_000_000_000,
        "regularMarketVolume": 80_000_000,
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("AAPL")

    assert result["price"] == 150.0
    assert result["name"] == "Apple Inc."
    assert result["pe_ttm"] == 28.5
    assert result["market_cap"] == 2_000_000_000_000


def test_fetch_full_returns_empty_on_zero_price(provider):
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = {"regularMarketPrice": 0}
        result = provider.fetch_full("AAPL")
    assert result == {}


def test_fetch_full_returns_empty_on_exception(provider):
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.side_effect = Exception("network error")
        result = provider.fetch_full("AAPL")
    assert result == {}


# ── fetch_fx ──────────────────────────────────────────────────────────────────


def test_fetch_fx_returns_rates(provider):
    fi = MagicMock()
    fi.last_price = 7.24
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        result = provider.fetch_fx({"USD": "USDCNY=X"})
    assert result["USD"] == 7.24
    assert result["CNY"] == 1.0


def test_fetch_fx_uses_cache_within_ttl(provider):
    fi = MagicMock()
    fi.last_price = 7.24
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        provider.fetch_fx({"USD": "USDCNY=X"})
        provider.fetch_fx({"USD": "USDCNY=X"})
    assert mock_yf.Ticker.call_count == 1  # second call used cache


def test_fetch_fx_refetches_after_ttl_expiry(provider):
    fi = MagicMock()
    fi.last_price = 7.24
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        # Seed cache with an expired entry
        provider._fx_cache["USD"] = (7.20, time.monotonic() - 120)
        provider.fetch_fx({"USD": "USDCNY=X"})
    assert mock_yf.Ticker.call_count == 1  # cache expired, re-fetched


def test_fetch_fx_falls_back_to_stale_cache_on_exception(provider):
    provider._fx_cache["USD"] = (7.20, time.monotonic() - 120)  # expired but present
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.side_effect = Exception("network error")
        result = provider.fetch_fx({"USD": "USDCNY=X"})
    assert result["USD"] == pytest.approx(7.20)


# ── _cn_etf_name / _fetch_cn_etf_name ────────────────────────────────────────


def _clear_name_cache():
    _cn_etf_name_cache.clear()


def test_cn_etf_name_returns_none_for_non_cn_symbol():
    assert _cn_etf_name("AAPL") is None
    assert _cn_etf_name("0700.HK") is None
    assert _cn_etf_name("BTC-USD") is None


def test_cn_etf_name_returns_none_for_short_code():
    assert _cn_etf_name("51031.SS") is None  # 5 digits


def test_cn_etf_name_returns_none_for_non_digit_code():
    assert _cn_etf_name("ABCDEF.SS") is None


def test_cn_etf_name_calls_fetch_for_valid_ss_code():
    _clear_name_cache()
    with patch(
        "fin.services.providers.yfinance_provider._fetch_cn_etf_name",
        return_value="纳指ETF嘉实",
    ) as mock_fetch:
        result = _cn_etf_name("510310.SS")
    assert result == "纳指ETF嘉实"
    mock_fetch.assert_called_once_with("510310")


def test_cn_etf_name_calls_fetch_for_valid_sz_code():
    _clear_name_cache()
    with patch(
        "fin.services.providers.yfinance_provider._fetch_cn_etf_name",
        return_value="创业板ETF",
    ) as mock_fetch:
        result = _cn_etf_name("159892.SZ")
    assert result == "创业板ETF"
    mock_fetch.assert_called_once_with("159892")


def test_fetch_cn_etf_name_returns_name_from_jsonp(tmp_path):
    _clear_name_cache()
    jsonp = 'jsonpgz({"fundcode":"510310","name":"纳指ETF嘉实","jzrq":"2024-01-01","dwjz":"1.234"});'.encode(
        "utf-8"
    )
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = jsonp
        mock_open.return_value = mock_resp
        result = _fetch_cn_etf_name("510310")
    assert result == "纳指ETF嘉实"


def test_fetch_cn_etf_name_returns_none_on_network_error():
    _clear_name_cache()
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        result = _fetch_cn_etf_name("510310")
    assert result is None


def test_fetch_cn_etf_name_caches_result():
    _clear_name_cache()
    jsonp = 'jsonpgz({"name":"纳指ETF嘉实"});'.encode("utf-8")
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = jsonp
        mock_open.return_value = mock_resp
        _fetch_cn_etf_name("510310")
        _fetch_cn_etf_name("510310")  # second call — should use cache
    assert mock_open.call_count == 1


def test_fetch_cn_etf_name_cache_hit_skips_http():
    _clear_name_cache()
    _cn_etf_name_cache["123456"] = ("沪深300ETF", time.monotonic() + _CN_ETF_NAME_TTL)
    with patch("urllib.request.urlopen") as mock_open:
        result = _fetch_cn_etf_name("123456")
    assert result == "沪深300ETF"
    mock_open.assert_not_called()


def test_fetch_cn_etf_name_refetches_after_ttl_expiry():
    _clear_name_cache()
    _cn_etf_name_cache["123456"] = ("old name", time.monotonic() - 1)  # expired
    jsonp = b'jsonpgz({"name":"new name"});'
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = jsonp
        mock_open.return_value = mock_resp
        result = _fetch_cn_etf_name("123456")
    assert result == "new name"
    mock_open.assert_called_once()


def test_fetch_cn_etf_name_caches_none_on_failure():
    _clear_name_cache()
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        _fetch_cn_etf_name("999999")
    assert "999999" in _cn_etf_name_cache
    assert _cn_etf_name_cache["999999"][0] is None


# ── fetch_live CN ETF name enrichment ─────────────────────────────────────────


def test_fetch_live_enriches_cn_etf_name(provider):
    fi = _make_fast_info()
    hist = _make_history()
    with (
        patch("fin.services.providers.yfinance_provider.yf") as mock_yf,
        patch(
            "fin.services.providers.yfinance_provider._fetch_cn_etf_name",
            return_value="纳指ETF嘉实",
        ),
    ):
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_live("510310.SS")
    assert result.get("name") == "纳指ETF嘉实"


def test_fetch_live_skips_name_when_not_cn_etf(provider):
    fi = _make_fast_info()
    hist = _make_history()
    with (
        patch("fin.services.providers.yfinance_provider.yf") as mock_yf,
        patch(
            "fin.services.providers.yfinance_provider._fetch_cn_etf_name"
        ) as mock_fetch,
    ):
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_live("AAPL")
    mock_fetch.assert_not_called()
    assert "name" not in result


# ── fetch_full CN ETF name enrichment ─────────────────────────────────────────


def test_fetch_full_enriches_cn_etf_name(provider):
    info = {
        "regularMarketPrice": 1.5,
        "regularMarketPreviousClose": 1.48,
        "shortName": "HARVEST FUND MANAGEMENT",
        "currency": "CNY",
        "quoteType": "ETF",
    }
    with (
        patch("fin.services.providers.yfinance_provider.yf") as mock_yf,
        patch(
            "fin.services.providers.yfinance_provider._fetch_cn_etf_name",
            return_value="纳指ETF嘉实",
        ),
    ):
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("510310.SS")
    assert result["name"] == "纳指ETF嘉实"


def test_fetch_full_falls_back_to_yf_name_when_em_fails(provider):
    info = {
        "regularMarketPrice": 1.5,
        "regularMarketPreviousClose": 1.48,
        "shortName": "HARVEST FUND MANAGEMENT",
        "currency": "CNY",
        "quoteType": "ETF",
    }
    with (
        patch("fin.services.providers.yfinance_provider.yf") as mock_yf,
        patch(
            "fin.services.providers.yfinance_provider._fetch_cn_etf_name",
            return_value=None,
        ),
    ):
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("510310.SS")
    assert result["name"] == "HARVEST FUND MANAGEMENT"


def test_fetch_full_asset_type_bond(provider):
    info = {
        "regularMarketPrice": 100.0,
        "regularMarketPreviousClose": 99.9,
        "currency": "USD",
        "quoteType": "MUTUALFUND",
        "category": "Short-Term Bond",
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("VBMFX")
    assert result["asset_type"] == "bond"


def test_fetch_full_asset_type_reit(provider):
    info = {
        "regularMarketPrice": 50.0,
        "regularMarketPreviousClose": 49.5,
        "currency": "USD",
        "quoteType": "EQUITY",
        "sector": "Real Estate",
        "category": "",
        "industry": "",
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("O")
    assert result["asset_type"] == "reit"


def test_fetch_full_asset_type_crypto(provider):
    info = {
        "regularMarketPrice": 95000.0,
        "regularMarketPreviousClose": 94000.0,
        "currency": "USD",
        "quoteType": "CRYPTOCURRENCY",
        "category": "",
        "sector": "",
        "industry": "",
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("BTC-USD")
    assert result["asset_type"] == "cryptocurrency"


def test_fetch_dividends_returns_empty_when_info_empty(provider):
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = {}
        result = provider.fetch_dividends("AAPL", "2024-01-01")
    assert result == {}


def test_fetch_full_asset_type_falls_back_to_equity(provider):
    info = {
        "regularMarketPrice": 10.0,
        "regularMarketPreviousClose": 9.9,
        "currency": "USD",
        "quoteType": "UNKNOWN_TYPE",
        "category": "",
        "sector": "",
        "industry": "",
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("XYZ")
    assert result["asset_type"] == "equity"


def test_fetch_full_pre_market_price(provider):
    info = {
        "regularMarketPrice": 150.0,
        "regularMarketPreviousClose": 148.0,
        "currency": "USD",
        "quoteType": "EQUITY",
        "marketState": "PRE",
        "preMarketPrice": 151.5,
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("AAPL")
    assert result["price"] == 151.5


def test_fetch_full_post_market_price(provider):
    info = {
        "regularMarketPrice": 150.0,
        "regularMarketPreviousClose": 148.0,
        "currency": "USD",
        "quoteType": "EQUITY",
        "marketState": "POST",
        "postMarketPrice": 149.0,
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = info
        result = provider.fetch_full("AAPL")
    assert result["price"] == 149.0


# ── _enrich_extended_hours ────────────────────────────────────────────────────


def test_enrich_extended_hours_pre_market(provider):
    fi = _make_fast_info(price=150.0, market_state="PRE")
    hist = _make_history()
    info_dict = {
        "marketState": "PRE",
        "regularMarketPrice": 150.0,
        "preMarketPrice": 152.0,
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        mock_yf.Ticker.return_value.info = info_dict
        result = provider.fetch_live("AAPL")
    assert result["price"] == 152.0


def test_enrich_extended_hours_post_market(provider):
    fi = _make_fast_info(price=150.0, market_state="POST")
    hist = _make_history()
    info_dict = {
        "marketState": "POST",
        "regularMarketPrice": 150.0,
        "postMarketPrice": 148.5,
    }
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        mock_yf.Ticker.return_value.info = info_dict
        result = provider.fetch_live("AAPL")
    assert result["price"] == 148.5


def test_fetch_live_uses_regular_close_when_last_price_is_none(provider):
    fi = _make_fast_info()
    fi.last_price = None
    hist = _make_history(close=145.0)
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_live("AAPL")
    assert result["price"] == 145.0


def test_enrich_extended_hours_exception_is_suppressed(provider):
    from unittest.mock import PropertyMock

    fi = _make_fast_info(market_state="PRE")
    hist = _make_history()
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        ticker_mock = MagicMock()
        ticker_mock.fast_info = fi
        ticker_mock.history.return_value = hist
        type(ticker_mock).info = PropertyMock(side_effect=Exception("info error"))
        mock_yf.Ticker.return_value = ticker_mock
        result = provider.fetch_live("AAPL")
    assert result["price"] == 150.0  # falls back to regular price


# ── fetch_history ──────────────────────────────────────────────────────────────


def test_fetch_history_returns_ohlc_rows(provider):
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)
    hist = pd.DataFrame(
        {"Close": [148.0, 150.0]}, index=pd.DatetimeIndex([yesterday, now])
    )
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.history.return_value = hist
        result = provider.fetch_history("AAPL", "2024-01-01", "2024-01-31")
    assert len(result) == 2
    assert result[-1]["close"] == 150.0
    assert "date" in result[0]


def test_fetch_history_returns_empty_on_empty_hist(provider):
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.history.return_value = pd.DataFrame()
        result = provider.fetch_history("AAPL", "2024-01-01", "2024-01-31")
    assert result == []


def test_fetch_history_returns_empty_on_exception(provider):
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.side_effect = Exception("network error")
        result = provider.fetch_history("AAPL", "2024-01-01", "2024-01-31")
    assert result == []


# ── fetch_fx: zero-price stale cache fallback ─────────────────────────────────


def test_fetch_fx_uses_stale_cache_when_price_is_zero(provider):
    provider._fx_cache["USD"] = (7.15, time.monotonic() - 120)  # expired but present
    fi = MagicMock()
    fi.last_price = 0.0
    fi.regularMarketPrice = None
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        result = provider.fetch_fx({"USD": "USDCNY=X"})
    assert result["USD"] == pytest.approx(7.15)
