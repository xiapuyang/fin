"""Tests for the dividend calendar feature.

Covers:
  - _annual_rate_from_history() pure function
  - _yf_parse_info() pure function
  - _yf_fetch_history() with mocked pandas Series
  - GET /api/dividends endpoint (cache logic, yfinance failure, filtering)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.api import app
from fin.database import Base, get_db
from fin.models.dividend_history import DividendHistoryModel
from fin.routers.holdings import (
    _annual_rate_from_history,
    _yf_fetch_history,
    _yf_parse_info,
)

# ── Shared test data ───────────────────────────────────────────────────────────

_AAPL_INFO = {
    "exDividendDate": 1710288000,  # 2024-03-13 UTC
    "dividendDate": 1710892800,  # 2024-03-20 UTC
    "dividendRate": 0.96,
}
_AAPL_DIVIDENDS = pd.Series(
    [0.24, 0.24, 0.24, 0.24],
    index=pd.DatetimeIndex(["2024-05-15", "2024-08-15", "2024-11-15", "2025-02-15"]),
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def div_env():
    """Yield (client, db) sharing the same in-memory SQLite database.

    Both the TestClient's internal sessions and the yielded db session point at
    the same StaticPool engine, so direct DB manipulations are visible to the
    next API call (after db.commit() + db.expire_all()).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db = Session()
    with patch("fin.api.init_db"):
        with patch("fin.api.start_price_updater"):
            with TestClient(app) as c:
                yield c, db
    db.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _mock_ticker(info=None, dividends=None):
    """Build a yf.Ticker mock with .info and .dividends configured."""
    mock = MagicMock()
    mock.info = info or {}
    mock.dividends = dividends if dividends is not None else pd.Series([], dtype=float)
    return mock


# ── _annual_rate_from_history ──────────────────────────────────────────────────


def test_annual_rate_empty_returns_none():
    assert _annual_rate_from_history([]) is None


def test_annual_rate_all_old_returns_none():
    old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")
    assert _annual_rate_from_history([{"date": old, "amount": 1.0}]) is None


def test_annual_rate_sums_recent():
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    history = [{"date": recent, "amount": 0.25}, {"date": recent, "amount": 0.75}]
    assert _annual_rate_from_history(history) == pytest.approx(1.0)


def test_annual_rate_excludes_old_entries():
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")
    history = [{"date": recent, "amount": 1.0}, {"date": old, "amount": 99.0}]
    assert _annual_rate_from_history(history) == pytest.approx(1.0)


def test_annual_rate_boundary_inclusive():
    exactly_365 = (datetime.now(timezone.utc) - timedelta(days=365)).strftime(
        "%Y-%m-%d"
    )
    assert _annual_rate_from_history(
        [{"date": exactly_365, "amount": 2.5}]
    ) == pytest.approx(2.5)


# ── _yf_parse_info ─────────────────────────────────────────────────────────────


def test_parse_info_all_fields():
    ex_date, pay_date, rate = _yf_parse_info(_AAPL_INFO)
    assert ex_date == "2024-03-13"
    assert pay_date == "2024-03-20"
    assert rate == pytest.approx(0.96)


def test_parse_info_missing_fields_return_none():
    ex_date, pay_date, rate = _yf_parse_info({})
    assert ex_date is None
    assert pay_date is None
    assert rate is None


def test_parse_info_zero_timestamp_is_none():
    # ex_ts=0 is falsy and must not produce "1970-01-01"
    ex_date, _, _ = _yf_parse_info({"exDividendDate": 0})
    assert ex_date is None


def test_parse_info_missing_dividend_rate():
    _, _, rate = _yf_parse_info({"exDividendDate": 1710288000})
    assert rate is None


# ── _yf_fetch_history ──────────────────────────────────────────────────────────


def _ticker_with(dates, amounts, tz=None):
    idx = pd.DatetimeIndex(dates)
    if tz:
        idx = idx.tz_localize(tz)
    mock = MagicMock()
    mock.dividends = pd.Series(amounts, index=idx)
    return mock


def test_fetch_history_empty_series():
    mock = MagicMock()
    mock.dividends = pd.Series([], dtype=float)
    assert _yf_fetch_history(mock, datetime(2020, 1, 1)) == []


def test_fetch_history_tz_naive_index():
    t = _ticker_with(["2023-06-15", "2023-09-15"], [0.25, 0.25])
    result = _yf_fetch_history(t, datetime(2023, 1, 1))
    assert result == [
        {"date": "2023-06-15", "amount": 0.25},
        {"date": "2023-09-15", "amount": 0.25},
    ]


def test_fetch_history_tz_aware_index():
    t = _ticker_with(["2023-06-15", "2023-09-15"], [0.30, 0.30], tz="UTC")
    result = _yf_fetch_history(t, datetime(2023, 1, 1))
    assert len(result) == 2
    assert result[0]["date"] == "2023-06-15"
    assert result[0]["amount"] == pytest.approx(0.30)
    assert result[1]["amount"] == pytest.approx(0.30)


def test_fetch_history_since_filter():
    t = _ticker_with(["2022-01-15", "2023-01-15", "2024-01-15"], [0.25, 0.25, 0.25])
    result = _yf_fetch_history(t, datetime(2023, 1, 1))
    assert len(result) == 2
    assert result[0]["date"] == "2023-01-15"


def test_fetch_history_timezone_aware_since_no_error():
    """since with tzinfo must not raise TypeError against naive pandas Timestamps."""
    t = _ticker_with(["2024-01-15"], [0.25])
    result = _yf_fetch_history(t, datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert len(result) == 1


# ── GET /api/dividends ─────────────────────────────────────────────────────────


def test_dividends_empty_symbols(div_env):
    client, _ = div_env
    assert client.get("/api/dividends").json() == {}


def test_dividends_cash_only(div_env):
    client, _ = div_env
    assert client.get("/api/dividends?symbols=CASH").json() == {}


def test_dividends_cash_filtered_from_mixed(div_env):
    client, _ = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch("fin.routers.holdings.yf.Ticker", return_value=ticker):
        data = client.get("/api/dividends?symbols=AAPL,CASH").json()
    assert "AAPL" in data
    assert "CASH" not in data


def test_dividends_new_symbol_fetches_and_caches(div_env):
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch("fin.routers.holdings.yf.Ticker", return_value=ticker):
        data = client.get("/api/dividends?symbols=AAPL").json()

    assert data["AAPL"]["ex_date"] == "2024-03-13"
    assert data["AAPL"]["annual_rate"] == pytest.approx(0.96)
    assert len(data["AAPL"]["history"]) == 4

    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    assert row is not None
    assert row.ex_date == "2024-03-13"
    assert row.fetched_at is not None


def test_dividends_fresh_cache_skips_yfinance(div_env):
    client, _ = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch("fin.routers.holdings.yf.Ticker", return_value=ticker):
        client.get("/api/dividends?symbols=AAPL")

    with patch("fin.routers.holdings.yf.Ticker") as mock_cls:
        data = client.get("/api/dividends?symbols=AAPL").json()

    mock_cls.assert_not_called()
    assert data["AAPL"]["ex_date"] == "2024-03-13"


def test_dividends_failure_returns_stale_data(div_env):
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch("fin.routers.holdings.yf.Ticker", return_value=ticker):
        client.get("/api/dividends?symbols=AAPL")

    # Expire the cached row so the next request tries yfinance
    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    row.fetched_at = "2020-01-01T00:00:00+00:00"
    db.commit()

    with patch(
        "fin.routers.holdings.yf.Ticker", side_effect=RuntimeError("network error")
    ):
        data = client.get("/api/dividends?symbols=AAPL").json()

    # Should fall back to the stale cached row, not return empty
    assert "AAPL" in data
    assert data["AAPL"]["ex_date"] == "2024-03-13"


def test_dividends_failure_does_not_update_fetched_at(div_env):
    """A yfinance failure must not advance fetched_at, so the symbol retries next request."""
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch("fin.routers.holdings.yf.Ticker", return_value=ticker):
        client.get("/api/dividends?symbols=AAPL")

    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    stale_ts = "2020-01-01T00:00:00+00:00"
    row.fetched_at = stale_ts
    db.commit()

    with patch(
        "fin.routers.holdings.yf.Ticker", side_effect=RuntimeError("network error")
    ):
        client.get("/api/dividends?symbols=AAPL")

    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    assert row.fetched_at == stale_ts


def test_dividends_new_symbol_failure_creates_no_row(div_env):
    """A failed first fetch for a new symbol must not create a poisoned shell row."""
    client, db = div_env
    with patch(
        "fin.routers.holdings.yf.Ticker", side_effect=RuntimeError("network error")
    ):
        data = client.get("/api/dividends?symbols=NEWCO").json()

    assert data == {}
    db.expire_all()
    assert db.query(DividendHistoryModel).filter_by(symbol="NEWCO").first() is None


def test_dividends_etf_no_dividend_rate_falls_back_to_history(div_env):
    """ETFs that omit dividendRate should derive annual_rate from last 12 months."""
    client, _ = div_env
    base = datetime.now(timezone.utc)
    monthly_dates = [
        (base - timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(11, -1, -1)
    ]
    dividends = pd.Series([0.10] * 12, index=pd.DatetimeIndex(monthly_dates))
    ticker = _mock_ticker(
        info={"quoteType": "ETF", "longName": "Vanguard Total World Bond ETF"},
        dividends=dividends,
    )
    with patch("fin.routers.holdings.yf.Ticker", return_value=ticker):
        data = client.get("/api/dividends?symbols=BNDW").json()

    assert "BNDW" in data
    assert data["BNDW"]["annual_rate"] == pytest.approx(1.2, rel=0.01)


def test_dividends_incremental_history_append(div_env):
    """Second fetch for a stale row appends new entries without duplicating old ones."""
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch("fin.routers.holdings.yf.Ticker", return_value=ticker):
        first = client.get("/api/dividends?symbols=AAPL").json()
    assert len(first["AAPL"]["history"]) == 4

    # Expire the cached row
    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    row.fetched_at = "2020-01-01T00:00:00+00:00"
    db.commit()

    # Ticker now has one additional entry at the end
    updated = pd.Series(
        [0.24, 0.24, 0.24, 0.24, 0.25],
        index=pd.DatetimeIndex(
            ["2024-05-15", "2024-08-15", "2024-11-15", "2025-02-15", "2025-05-15"]
        ),
    )
    updated_ticker = _mock_ticker(info=_AAPL_INFO, dividends=updated)
    with patch("fin.routers.holdings.yf.Ticker", return_value=updated_ticker):
        second = client.get("/api/dividends?symbols=AAPL").json()

    # Should have 4 original + 1 new = 5, no duplicates
    assert len(second["AAPL"]["history"]) == 5
    dates = [h["date"] for h in second["AAPL"]["history"]]
    assert "2025-05-15" in dates
    assert dates.count("2024-05-15") == 1
