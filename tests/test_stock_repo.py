"""Tests for StockSQLiteRepository."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.database import Base
from fin.repositories.stock_sqlite import StockSQLiteRepository


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


def test_get_by_symbol_returns_none_when_missing(db):
    repo = StockSQLiteRepository(db)
    assert repo.get_by_symbol("AAPL") is None


def test_upsert_creates_new_record(db):
    repo = StockSQLiteRepository(db)
    repo.upsert("AAPL", {"price": 150.0, "prev_close": 148.0, "currency": "USD"})
    stock = repo.get_by_symbol("AAPL")
    assert stock is not None
    assert stock.price == 150.0
    assert stock.currency == "USD"


def test_upsert_updates_existing_record(db):
    repo = StockSQLiteRepository(db)
    repo.upsert("AAPL", {"price": 150.0})
    repo.upsert("AAPL", {"price": 155.0})
    assert repo.get_by_symbol("AAPL").price == 155.0


def test_upsert_ignores_none_values(db):
    repo = StockSQLiteRepository(db)
    repo.upsert("AAPL", {"price": 150.0, "pe_ttm": 25.0})
    repo.upsert("AAPL", {"price": 151.0, "pe_ttm": None})
    stock = repo.get_by_symbol("AAPL")
    assert stock.price == 151.0
    assert stock.pe_ttm == 25.0  # not overwritten by None


def test_upsert_sets_updated_at(db):
    repo = StockSQLiteRepository(db)
    before = datetime.utcnow() - timedelta(seconds=1)
    repo.upsert("AAPL", {"price": 150.0})
    stock = repo.get_by_symbol("AAPL")
    assert stock.updated_at >= before


def test_get_all_returns_all_stocks(db):
    repo = StockSQLiteRepository(db)
    repo.upsert("AAPL", {"price": 150.0})
    repo.upsert("GOOG", {"price": 180.0})
    assert len(repo.get_all()) == 2
