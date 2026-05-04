"""Tests for QuoteService — DB-first, live fallback, write-through."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.database import Base
from fin.repositories.stock_sqlite import StockSQLiteRepository
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
    with patch("fin.services.quote._fetch_live", return_value={}):
        result = QuoteService(db).get_quote("AAPL")
    assert result is None


def test_get_quote_reads_from_db_when_fresh(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=60)
    with patch("fin.services.quote._fetch_live") as mock_live:
        result = QuoteService(db).get_quote("AAPL")
    mock_live.assert_not_called()
    assert result["price"] == 150.0


def test_get_quote_fetches_live_when_stale(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=400)
    live_data = {"price": 155.0, "prev_close": 150.0, "currency": "USD"}
    with patch("fin.services.quote._fetch_live", return_value=live_data):
        result = QuoteService(db).get_quote("AAPL")
    assert result["price"] == 155.0


def test_get_quote_updates_db_after_live_fetch(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=400)
    live_data = {"price": 155.0, "prev_close": 150.0, "currency": "USD"}
    with patch("fin.services.quote._fetch_live", return_value=live_data):
        QuoteService(db).get_quote("AAPL")
    assert StockSQLiteRepository(db).get_by_symbol("AAPL").price == 155.0


def test_get_quote_falls_back_to_stale_db_when_live_fails(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=400)
    with patch("fin.services.quote._fetch_live", return_value={}):
        result = QuoteService(db).get_quote("AAPL")
    assert result["price"] == 150.0


def test_get_quote_returns_change_pct(db):
    _seed_stock(db, "AAPL", price=150.0, prev_close=100.0, age_seconds=60)
    result = QuoteService(db).get_quote("AAPL")
    assert result["change_pct"] == pytest.approx(50.0)


def test_get_quote_normalizes_symbol(db):
    _seed_stock(db, "^GSPC", price=5000.0, age_seconds=60)
    result = QuoteService(db).get_quote(".SPX")
    assert result["price"] == 5000.0


def test_get_quote_fetches_live_when_db_empty(db):
    live_data = {"price": 155.0, "prev_close": 150.0, "currency": "USD"}
    with patch("fin.services.quote._fetch_live", return_value=live_data):
        result = QuoteService(db).get_quote("AAPL")
    assert result["price"] == 155.0
