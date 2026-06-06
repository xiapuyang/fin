"""Tests for ChinaFundProvider."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fin.services.providers.china_fund_provider import ChinaFundProvider


@pytest.fixture()
def provider():
    return ChinaFundProvider()


def _make_nav_df(rows=None):
    if rows is None:
        rows = [
            {
                "净值日期": "2026-05-04",
                "单位净值": "1.2327",
                "累计净值": "2.5000",
                "日增长率": "0.10",
            },
            {
                "净值日期": "2026-05-05",
                "单位净值": "1.2456",
                "累计净值": "2.5129",
                "日增长率": "1.05",
            },
        ]
    return pd.DataFrame(rows)


def _make_jsonp_response(code="013308", gsz="1.2690", dwjz="1.2327", name="Test Fund"):
    payload = json.dumps(
        {"fundcode": code, "name": name, "dwjz": dwjz, "gsz": gsz, "gszzl": "2.95"}
    )
    text = f"jsonpgz({payload});"
    mock_resp = MagicMock()
    mock_resp.read.return_value = text.encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── supports ──────────────────────────────────────────────────────────────────


def test_supports_open_end_fund_code(provider):
    assert provider.supports("013308") is True


def test_supports_bare_etf_code(provider):
    assert provider.supports("510310") is True


def test_supports_rejects_suffixed_etf(provider):
    assert provider.supports("510310.SS") is False
    assert provider.supports("159892.SZ") is False


def test_supports_rejects_non_cn_symbols(provider):
    assert provider.supports("AAPL") is False
    assert provider.supports("^GSPC") is False


# ── fetch_live ────────────────────────────────────────────────────────────────


def test_fetch_live_returns_nav_dict(provider):
    mock_resp = _make_jsonp_response()
    with patch(
        "fin.services.providers.china_fund_provider.urllib.request.urlopen",
        return_value=mock_resp,
    ):
        result = provider.fetch_live("013308")

    assert result["price"] == pytest.approx(1.2690)
    assert result["prev_close"] == pytest.approx(1.2327)
    assert result["currency"] == "CNY"
    assert result["market_state"] is None
    assert result["name"] == "Test Fund"


def test_fetch_live_returns_empty_on_missing_gsz(provider):
    payload = json.dumps({"fundcode": "013308", "dwjz": "1.2327"})
    text = f"jsonpgz({payload});"
    mock_resp = MagicMock()
    mock_resp.read.return_value = text.encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch(
        "fin.services.providers.china_fund_provider.urllib.request.urlopen",
        return_value=mock_resp,
    ):
        result = provider.fetch_live("013308")
    assert result == {}


def test_fetch_live_returns_empty_on_missing_dwjz(provider):
    payload = json.dumps({"fundcode": "013308", "gsz": "1.2690"})
    text = f"jsonpgz({payload});"
    mock_resp = MagicMock()
    mock_resp.read.return_value = text.encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch(
        "fin.services.providers.china_fund_provider.urllib.request.urlopen",
        return_value=mock_resp,
    ):
        result = provider.fetch_live("013308")
    assert result == {}


def test_fetch_live_returns_empty_on_non_finite_nav(provider):
    mock_resp = _make_jsonp_response(gsz="NaN", dwjz="1.2327")
    with patch(
        "fin.services.providers.china_fund_provider.urllib.request.urlopen",
        return_value=mock_resp,
    ):
        result = provider.fetch_live("013308")
    assert result == {}


def test_fetch_live_returns_empty_on_network_error(provider):
    with patch(
        "fin.services.providers.china_fund_provider.urllib.request.urlopen",
        side_effect=Exception("connection refused"),
    ):
        result = provider.fetch_live("999999")
    assert result == {}


def test_fetch_live_returns_empty_on_malformed_response(provider):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"not-jsonp-format"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch(
        "fin.services.providers.china_fund_provider.urllib.request.urlopen",
        return_value=mock_resp,
    ):
        result = provider.fetch_live("013308")
    assert result == {}


# ── fetch_full ────────────────────────────────────────────────────────────────


def test_fetch_full_returns_latest_nav(provider):
    df = _make_nav_df()
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.return_value = df
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_full("013308")

    assert result["price"] == pytest.approx(1.2456)
    assert result["prev_close"] == pytest.approx(1.2327)
    assert result["currency"] == "CNY"
    assert result["asset_type"] == "mutualfund"
    assert result["market_state"] is None


def test_fetch_full_returns_empty_on_empty_df(provider):
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.return_value = pd.DataFrame()
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_full("013308")
    assert result == {}


def test_fetch_full_single_row_uses_same_price_for_prev_close(provider):
    df = _make_nav_df(
        rows=[
            {
                "净值日期": "2026-05-05",
                "单位净值": "1.2456",
                "累计净值": "2.5129",
                "日增长率": "0.00",
            }
        ]
    )
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.return_value = df
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_full("013308")

    assert result["price"] == pytest.approx(1.2456)
    assert result["prev_close"] == pytest.approx(1.2456)


def test_fetch_full_returns_empty_on_exception(provider):
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.side_effect = Exception("akshare error")
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_full("999999")
    assert result == {}


# ── fetch_fx ──────────────────────────────────────────────────────────────────


def test_fetch_fx_raises_not_implemented(provider):
    with pytest.raises(NotImplementedError):
        provider.fetch_fx({"USD": "USDCNY=X"})


# ── additional coverage ───────────────────────────────────────────────────────


def test_fetch_live_returns_empty_when_price_is_zero(provider):
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_jsonp_response(gsz="0", dwjz="1.2327")
        result = provider.fetch_live("013308")
    assert result == {}


def test_fetch_dividends_returns_empty(provider):
    result = provider.fetch_dividends("013308", "2024-01-01")
    assert result == {}


def test_fetch_history_returns_rows(provider):
    df = _make_nav_df()
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.return_value = df
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_history("013308", "2026-05-01", "2026-05-10")
    assert len(result) == 2
    assert result[0]["close"] == pytest.approx(1.2327)
    assert result[0]["date"] == "2026-05-04"


def test_fetch_history_returns_empty_on_empty_df(provider):
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.return_value = pd.DataFrame()
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_history("013308", "2026-05-01", "2026-05-10")
    assert result == []


def test_fetch_history_returns_empty_on_timeout(provider):
    import concurrent.futures

    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.side_effect = concurrent.futures.TimeoutError()
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_history("013308", "2026-05-01", "2026-05-10")
    assert result == []


def test_fetch_history_returns_empty_on_exception(provider):
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.side_effect = Exception("network error")
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_history("013308", "2026-05-01", "2026-05-10")
    assert result == []


def test_fetch_history_returns_empty_when_akshare_missing(provider):
    with patch.dict("sys.modules", {"akshare": None}):
        result = provider.fetch_history("013308", "2026-05-01", "2026-05-10")
    assert result == []


def test_fetch_full_returns_empty_when_price_is_zero(provider):
    rows = [
        {"净值日期": "2026-05-04", "单位净值": "0", "累计净值": "2.5", "日增长率": "0"},
    ]
    df = pd.DataFrame(rows)
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.return_value = df
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_full("013308")
    assert result == {}


def test_fetch_full_returns_empty_on_timeout(provider):
    import concurrent.futures

    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.side_effect = concurrent.futures.TimeoutError()
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_full("013308")
    assert result == {}


def test_fetch_full_returns_empty_when_akshare_missing(provider):
    with patch.dict("sys.modules", {"akshare": None}):
        result = provider.fetch_full("013308")
    assert result == {}


def test_fetch_history_filters_out_of_range_dates(provider):
    rows = [
        {
            "净值日期": "2026-04-30",
            "单位净值": "1.20",
            "累计净值": "2.40",
            "日增长率": "0",
        },  # before start
        {
            "净值日期": "2026-05-04",
            "单位净值": "1.23",
            "累计净值": "2.50",
            "日增长率": "0.10",
        },  # in range
        {
            "净值日期": "2026-05-10",
            "单位净值": "1.25",
            "累计净值": "2.52",
            "日增长率": "0",
        },  # >= end, excluded
    ]
    mock_ak = MagicMock()
    mock_ak.fund_open_fund_info_em.return_value = pd.DataFrame(rows)
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        result = provider.fetch_history("013308", "2026-05-01", "2026-05-10")
    assert len(result) == 1
    assert result[0]["date"] == "2026-05-04"
