"""Tests for YFinanceProvider."""

import time
from unittest.mock import MagicMock, patch

import pytest

from fin.services.providers.yfinance_provider import YFinanceProvider


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
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        result = provider.fetch_live("AAPL")

    assert result["price"] == 150.0
    assert result["prev_close"] == 148.0
    assert result["market_state"] == "REGULAR"
    assert "open_price" in result


def test_fetch_live_returns_empty_on_zero_price(provider):
    fi = _make_fast_info(price=0.0)
    with patch("fin.services.providers.yfinance_provider.yf") as mock_yf:
        mock_yf.Ticker.return_value.fast_info = fi
        result = provider.fetch_live("AAPL")
    assert result == {}


def test_fetch_live_dot_to_dash_retry(provider):
    fi = _make_fast_info()
    call_count = {"n": 0}

    def make_ticker(sym):
        t = MagicMock()
        call_count["n"] += 1
        if sym == "BRK.B":
            t.fast_info = _make_fast_info(price=0.0)  # first call fails
        else:
            t.fast_info = fi
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
