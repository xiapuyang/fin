"""Tests for PriceUpdater symbol collection and update logic."""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.database import Base
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin.repositories.stock_sqlite import StockSQLiteRepository
from fin.schemas.alert import AlertCreate
from fin.services.price_updater import collect_symbols, run_update_cycle


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


def test_collect_symbols_reads_symbols_json(tmp_path, monkeypatch):
    symbols_file = tmp_path / "symbols.json"
    symbols_file.write_text(
        json.dumps(
            {
                "US": [
                    {"code": "AAPL", "name": "Apple"},
                    {"code": "GOOG", "name": "Google"},
                ]
            }
        )
    )
    import fin.services.price_updater as pu

    monkeypatch.setattr(pu, "SYMBOLS_PATH", symbols_file)

    with patch("fin.services.price_updater._alert_symbols", return_value=set()):
        with patch("fin.services.price_updater._portfolio_symbols", return_value=set()):
            symbols = collect_symbols()

    assert "AAPL" in symbols
    assert "GOOG" in symbols


def test_collect_symbols_includes_alert_symbols(tmp_path, monkeypatch, db):
    symbols_file = tmp_path / "symbols.json"
    symbols_file.write_text(json.dumps({}))
    import fin.services.price_updater as pu

    monkeypatch.setattr(pu, "SYMBOLS_PATH", symbols_file)

    AlertSQLiteRepository(db).create(
        AlertCreate(symbol="TSLA", name="t", condition="price_lte", value=100.0)
    )
    with patch("fin.services.price_updater._alert_symbols", return_value={"TSLA"}):
        with patch("fin.services.price_updater._portfolio_symbols", return_value=set()):
            symbols = collect_symbols()

    assert "TSLA" in symbols


def test_collect_symbols_normalizes_aliases(tmp_path, monkeypatch):
    symbols_file = tmp_path / "symbols.json"
    symbols_file.write_text(json.dumps({"Index": [{"code": ".SPX", "name": "S&P"}]}))
    import fin.services.price_updater as pu

    monkeypatch.setattr(pu, "SYMBOLS_PATH", symbols_file)

    with patch("fin.services.price_updater._alert_symbols", return_value=set()):
        with patch("fin.services.price_updater._portfolio_symbols", return_value=set()):
            symbols = collect_symbols()

    assert "^GSPC" in symbols
    assert ".SPX" not in symbols


def test_run_update_cycle_upserts_into_db(db, tmp_path, monkeypatch):
    symbols_file = tmp_path / "symbols.json"
    symbols_file.write_text(json.dumps({"US": [{"code": "AAPL", "name": "Apple"}]}))
    import fin.services.price_updater as pu

    monkeypatch.setattr(pu, "SYMBOLS_PATH", symbols_file)

    full_data = {"price": 150.0, "prev_close": 148.0, "currency": "USD"}
    with patch("fin.services.price_updater.fetch_full_quote", return_value=full_data):
        with patch("fin.services.price_updater._alert_symbols", return_value=set()):
            with patch(
                "fin.services.price_updater._portfolio_symbols", return_value=set()
            ):
                run_update_cycle(db)

    assert StockSQLiteRepository(db).get_by_symbol("AAPL").price == 150.0


def test_run_update_cycle_skips_failed_symbols(db, tmp_path, monkeypatch):
    symbols_file = tmp_path / "symbols.json"
    symbols_file.write_text(json.dumps({"US": [{"code": "AAPL", "name": "Apple"}]}))
    import fin.services.price_updater as pu

    monkeypatch.setattr(pu, "SYMBOLS_PATH", symbols_file)

    with patch("fin.services.price_updater.fetch_full_quote", return_value={}):
        with patch("fin.services.price_updater._alert_symbols", return_value=set()):
            with patch(
                "fin.services.price_updater._portfolio_symbols", return_value=set()
            ):
                run_update_cycle(db)  # should not raise

    assert StockSQLiteRepository(db).get_by_symbol("AAPL") is None
