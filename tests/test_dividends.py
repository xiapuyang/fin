"""Tests for the dividend calendar feature.

Covers:
  - _annual_rate_from_history() pure function
  - YFinanceProvider.fetch_dividends() info + history parsing (mocked yf.Ticker)
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
from fin.routers.holdings import _annual_rate_from_history
from fin.services.providers.yfinance_provider import YFinanceProvider

# ── Shared test data ───────────────────────────────────────────────────────────

_AAPL_INFO = {
    "exDividendDate": 1710288000,  # 2024-03-13 UTC
    "dividendDate": 1710892800,  # 2024-03-20 UTC
    "dividendRate": 0.96,
}

# Dividend dates are computed relative to "today" at module load so the lookback
# window in _yf_fetch_history (~2 years) never times them out.
_TODAY = datetime.now(timezone.utc).date()


def _days_ago(n: int) -> str:
    return (_TODAY - timedelta(days=n)).strftime("%Y-%m-%d")


_AAPL_HISTORY_DATES = [
    _days_ago(360),
    _days_ago(270),
    _days_ago(180),
    _days_ago(90),
]
_AAPL_NEW_DATE = _days_ago(7)

_AAPL_DIVIDENDS = pd.Series(
    [0.24, 0.24, 0.24, 0.24],
    index=pd.DatetimeIndex(_AAPL_HISTORY_DATES),
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


_STUB_INFO = {"quoteType": "EQUITY"}  # minimal truthy info; no dividend fields


def _mock_ticker(info=None, dividends=None):
    """Build a yf.Ticker mock with .info and .dividends configured."""
    mock = MagicMock()
    mock.info = info if info is not None else _STUB_INFO
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


# ── YFinanceProvider.fetch_dividends — info parsing ───────────────────────────
# These replace the old _yf_parse_info unit tests now that the logic is inlined
# into YFinanceProvider.fetch_dividends().


def test_fetch_dividends_parses_all_info_fields():
    t = _mock_ticker(info=_AAPL_INFO)
    result = _fetch_dividends(t, "2024-01-01")
    assert result["ex_date"] == "2024-03-13"
    assert result["pay_date"] == "2024-03-20"
    assert result["annual_rate"] == pytest.approx(0.96)


def test_fetch_dividends_missing_info_fields_are_none():
    # Truthy but empty of dividend fields → all None, not early-exit {}
    t = _mock_ticker(info=_STUB_INFO)
    result = _fetch_dividends(t, "2024-01-01")
    assert result["ex_date"] is None
    assert result["pay_date"] is None
    assert result["annual_rate"] is None


def test_fetch_dividends_zero_timestamp_is_none():
    # ex_ts=0 is falsy and must not produce "1970-01-01"
    t = _mock_ticker(info={**_STUB_INFO, "exDividendDate": 0})
    result = _fetch_dividends(t, "2024-01-01")
    assert result["ex_date"] is None


def test_fetch_dividends_missing_dividend_rate_is_none():
    t = _mock_ticker(info={**_STUB_INFO, "exDividendDate": 1710288000})
    result = _fetch_dividends(t, "2024-01-01")
    assert result["annual_rate"] is None


# ── YFinanceProvider.fetch_dividends — history parsing ────────────────────────


def _ticker_with_history(dates, amounts, tz=None, info=None):
    """Build a ticker mock whose .dividends has a custom-indexed pandas Series."""
    idx = pd.DatetimeIndex(dates)
    if tz:
        idx = idx.tz_localize(tz)
    return _mock_ticker(
        info=info if info is not None else _STUB_INFO,
        dividends=pd.Series(amounts, index=idx),
    )


def _fetch_dividends(ticker, since: str) -> dict:
    """Call YFinanceProvider.fetch_dividends with a pre-built mock ticker."""
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
        return YFinanceProvider().fetch_dividends("AAPL", since)


def test_fetch_dividends_empty_series():
    t = _mock_ticker()
    result = _fetch_dividends(t, "2020-01-01")
    assert result["history"] == []


def test_fetch_dividends_tz_naive_index():
    t = _ticker_with_history(["2023-06-15", "2023-09-15"], [0.25, 0.25])
    result = _fetch_dividends(t, "2023-01-01")
    assert result["history"] == [
        {"date": "2023-06-15", "amount": 0.25},
        {"date": "2023-09-15", "amount": 0.25},
    ]


def test_fetch_dividends_tz_aware_index():
    t = _ticker_with_history(["2023-06-15", "2023-09-15"], [0.30, 0.30], tz="UTC")
    result = _fetch_dividends(t, "2023-01-01")
    assert len(result["history"]) == 2
    assert result["history"][0]["date"] == "2023-06-15"
    assert result["history"][0]["amount"] == pytest.approx(0.30)


def test_fetch_dividends_since_filter():
    t = _ticker_with_history(
        ["2022-01-15", "2023-01-15", "2024-01-15"], [0.25, 0.25, 0.25]
    )
    result = _fetch_dividends(t, "2023-01-01")
    assert len(result["history"]) == 2
    assert result["history"][0]["date"] == "2023-01-15"


def test_fetch_dividends_returns_ex_and_pay_dates():
    t = _mock_ticker(
        info={
            "exDividendDate": 1710288000,  # 2024-03-13 UTC
            "dividendDate": 1710892800,  # 2024-03-20 UTC
            "dividendRate": 0.96,
        }
    )
    result = _fetch_dividends(t, "2024-01-01")
    assert result["ex_date"] == "2024-03-13"
    assert result["pay_date"] == "2024-03-20"
    assert result["annual_rate"] == pytest.approx(0.96)


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
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
        data = client.get("/api/dividends?symbols=AAPL,CASH").json()
    assert "AAPL" in data
    assert "CASH" not in data


def test_dividends_new_symbol_fetches_and_caches(div_env):
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
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
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
        client.get("/api/dividends?symbols=AAPL")

    with patch("fin.services.providers.yfinance_provider.yf.Ticker") as mock_cls:
        data = client.get("/api/dividends?symbols=AAPL").json()

    mock_cls.assert_not_called()
    assert data["AAPL"]["ex_date"] == "2024-03-13"


def test_dividends_failure_returns_stale_data(div_env):
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
        client.get("/api/dividends?symbols=AAPL")

    # Expire the cached row so the next request tries yfinance
    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    row.fetched_at = "2020-01-01T00:00:00+00:00"
    db.commit()

    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker",
        side_effect=RuntimeError("network error"),
    ):
        data = client.get("/api/dividends?symbols=AAPL").json()

    # Should fall back to the stale cached row, not return empty
    assert "AAPL" in data
    assert data["AAPL"]["ex_date"] == "2024-03-13"


def test_dividends_failure_does_not_update_fetched_at(div_env):
    """A yfinance failure must not advance fetched_at, so the symbol retries next request."""
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
        client.get("/api/dividends?symbols=AAPL")

    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    stale_ts = "2020-01-01T00:00:00+00:00"
    row.fetched_at = stale_ts
    db.commit()

    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker",
        side_effect=RuntimeError("network error"),
    ):
        client.get("/api/dividends?symbols=AAPL")

    db.expire_all()
    row = db.query(DividendHistoryModel).filter_by(symbol="AAPL").first()
    assert row.fetched_at == stale_ts


def test_dividends_new_symbol_failure_creates_no_row(div_env):
    """A failed first fetch for a new symbol must not create a poisoned shell row."""
    client, db = div_env
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker",
        side_effect=RuntimeError("network error"),
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
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
        data = client.get("/api/dividends?symbols=BNDW").json()

    assert "BNDW" in data
    assert data["BNDW"]["annual_rate"] == pytest.approx(1.2, rel=0.01)


def test_dividends_incremental_history_append(div_env):
    """Second fetch for a stale row appends new entries without duplicating old ones."""
    client, db = div_env
    ticker = _mock_ticker(info=_AAPL_INFO, dividends=_AAPL_DIVIDENDS)
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker", return_value=ticker
    ):
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
        index=pd.DatetimeIndex([*_AAPL_HISTORY_DATES, _AAPL_NEW_DATE]),
    )
    updated_ticker = _mock_ticker(info=_AAPL_INFO, dividends=updated)
    with patch(
        "fin.services.providers.yfinance_provider.yf.Ticker",
        return_value=updated_ticker,
    ):
        second = client.get("/api/dividends?symbols=AAPL").json()

    # Should have 4 original + 1 new = 5, no duplicates
    assert len(second["AAPL"]["history"]) == 5
    dates = [h["date"] for h in second["AAPL"]["history"]]
    assert _AAPL_NEW_DATE in dates
    assert dates.count(_AAPL_HISTORY_DATES[0]) == 1
