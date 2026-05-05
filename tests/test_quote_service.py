"""Tests for QuoteService — DB-first, live fallback, write-through."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.database import Base
from fin.repositories.stock_sqlite import StockSQLiteRepository
from fin.services.providers.base import QuoteProvider
from fin.services.quote import QuoteService, normalize_symbol


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _mock_provider(supports=True, live_data=None, full_data=None, fx_data=None):
    """Build a mock QuoteProvider with configurable return values."""
    p = MagicMock(spec=QuoteProvider)
    p.supports.return_value = supports
    p.fetch_live.return_value = live_data or {}
    p.fetch_full.return_value = full_data or {}
    if fx_data is not None:
        p.fetch_fx.return_value = fx_data
    else:
        p.fetch_fx.side_effect = NotImplementedError()
    return p


def _seed_stock(db, symbol, price=150.0, prev_close=148.0, age_seconds=0):
    repo = StockSQLiteRepository(db)
    stock = repo.upsert(
        symbol, {"price": price, "prev_close": prev_close, "currency": "USD"}
    )
    stock.updated_at = datetime.utcnow() - timedelta(seconds=age_seconds)
    db.commit()
    return stock


# ── normalize_symbol ──────────────────────────────────────────────────────────


def test_normalize_symbol_aliases():
    assert normalize_symbol(".SPX") == "^GSPC"
    assert normalize_symbol(".NDX") == "^NDX"
    assert normalize_symbol(".DJI") == "^DJI"


def test_normalize_symbol_uppercases():
    assert normalize_symbol("aapl") == "AAPL"


# ── QuoteService.get_quote ────────────────────────────────────────────────────


def test_get_quote_returns_none_when_no_data_and_live_fails(db):
    provider = _mock_provider(live_data={})
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result is None


def test_get_quote_reads_from_db_when_fresh(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=60)
    provider = _mock_provider()
    result = QuoteService(db, [provider]).get_quote("AAPL")
    provider.fetch_live.assert_not_called()
    assert result["price"] == 150.0


def test_get_quote_fetches_live_when_stale(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=400)
    live_data = {"price": 155.0, "prev_close": 150.0, "currency": "USD"}
    provider = _mock_provider(live_data=live_data)
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result["price"] == 155.0


def test_get_quote_updates_db_after_live_fetch(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=400)
    live_data = {"price": 155.0, "prev_close": 150.0, "currency": "USD"}
    provider = _mock_provider(live_data=live_data)
    QuoteService(db, [provider]).get_quote("AAPL")
    assert StockSQLiteRepository(db).get_by_symbol("AAPL").price == 155.0


def test_get_quote_falls_back_to_stale_db_when_live_fails(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=400)
    provider = _mock_provider(live_data={})
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result["price"] == 150.0


def test_get_quote_returns_change_pct(db):
    _seed_stock(db, "AAPL", price=150.0, prev_close=100.0, age_seconds=60)
    provider = _mock_provider()
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result["change_pct"] == pytest.approx(50.0)


def test_get_quote_normalizes_symbol(db):
    _seed_stock(db, "^GSPC", price=5000.0, age_seconds=60)
    provider = _mock_provider()
    result = QuoteService(db, [provider]).get_quote(".SPX")
    assert result["price"] == 5000.0


def test_get_quote_fetches_live_when_db_empty(db):
    live_data = {"price": 155.0, "prev_close": 150.0, "currency": "USD"}
    provider = _mock_provider(live_data=live_data)
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result["price"] == 155.0


def test_get_quote_includes_market_state_in_return(db):
    live_data = {
        "price": 155.0,
        "prev_close": 150.0,
        "currency": "USD",
        "market_state": "REGULAR",
    }
    provider = _mock_provider(live_data=live_data)
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert "market_state" in result
    assert result["market_state"] == "REGULAR"


def test_get_quote_routes_to_china_fund_provider(db):
    cn_provider = _mock_provider(
        supports=True,
        live_data={
            "price": 1.25,
            "prev_close": 1.23,
            "currency": "CNY",
            "market_state": None,
        },
    )
    us_provider = _mock_provider(supports=False)
    result = QuoteService(db, [cn_provider, us_provider]).get_quote("013308")
    cn_provider.fetch_live.assert_called_once()
    us_provider.fetch_live.assert_not_called()
    assert result["price"] == pytest.approx(1.25)


def test_get_quote_returns_none_when_no_provider_supports(db):
    provider = _mock_provider(supports=False)
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result is None


def test_get_quote_stale_db_fallback_when_live_returns_empty(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=400)
    provider = _mock_provider(live_data={})
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result["price"] == 150.0
    assert "market_state" in result


# ── QuoteService.get_full_quote ───────────────────────────────────────────────


def test_get_full_quote_delegates_to_provider(db):
    full_data = {"price": 150.0, "prev_close": 148.0, "name": "Apple", "pe_ttm": 28.5}
    provider = _mock_provider(full_data=full_data)
    result = QuoteService(db, [provider]).get_full_quote("AAPL")
    assert result["pe_ttm"] == 28.5
    provider.fetch_full.assert_called_once_with("AAPL")


# ── QuoteService.get_fx ───────────────────────────────────────────────────────


def test_get_fx_skips_provider_with_not_implemented_and_uses_next(db):
    cn_provider = _mock_provider(fx_data=None)  # raises NotImplementedError
    cn_provider.fetch_fx.side_effect = NotImplementedError()
    us_provider = _mock_provider(fx_data={"USD": 7.24, "CNY": 1.0})
    result = QuoteService(db, [cn_provider, us_provider]).get_fx({"USD": "USDCNY=X"})
    assert result["USD"] == pytest.approx(7.24)
    cn_provider.fetch_fx.assert_called_once()
    us_provider.fetch_fx.assert_called_once()


def test_get_fx_raises_runtime_error_when_no_provider_supports(db):
    provider = _mock_provider()
    provider.fetch_fx.side_effect = NotImplementedError()
    with pytest.raises(RuntimeError, match="no provider supports FX"):
        QuoteService(db, [provider]).get_fx({"USD": "USDCNY=X"})
