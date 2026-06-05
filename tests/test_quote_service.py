"""Tests for QuoteService — DB-first, live fallback, write-through."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.database import Base, import_all_models
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
    import_all_models()
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


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Already-suffixed A-share / HK — pass through unchanged
        ("002594.SZ", "002594.SZ"),
        ("0700.HK", "0700.HK"),
        # Shenzhen ETFs: bare 6-digit codes in the 150-169 prefix range → .SZ
        ("159501", "159501.SZ"),
        ("159892", "159892.SZ"),
        # Shanghai ETFs: 500-588 prefix → .SS
        ("510310", "510310.SS"),
        ("513260", "513260.SS"),
        ("513870", "513870.SS"),
        # OTC CN mutual fund: 013xxx doesn't match any exchange range → stays bare
        ("013308", "013308"),
        # US equities and ETFs — uppercase only, no suffix added
        ("AAPL", "AAPL"),
        ("BNDW", "BNDW"),
        ("BRK-B", "BRK-B"),
        ("BSV", "BSV"),
        ("COIN", "COIN"),
        ("GOOG", "GOOG"),
        ("META", "META"),
        ("MSFT", "MSFT"),
        ("NVDA", "NVDA"),
        ("PDD", "PDD"),
        ("QQQ", "QQQ"),
        ("TSM", "TSM"),
        ("VT", "VT"),
        ("VTV", "VTV"),
        # Crypto
        ("BTC-USD", "BTC-USD"),
        # Canadian (TSX / NEO) — suffix already present, pass through
        ("TEC.TO", "TEC.TO"),
        ("VEQT.TO", "VEQT.TO"),
        ("VFV.TO", "VFV.TO"),
        ("VGAB.NE", "VGAB.NE"),
        ("ZNQ.TO", "ZNQ.TO"),
    ],
)
def test_normalize_symbol_holdings(raw, expected):
    """normalize_symbol round-trips correctly for every symbol in the live portfolio."""
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize(
    "symbol,is_cn_fund",
    [
        # OTC CN fund → ChinaFundProvider (supports bare 6-digit code)
        ("013308", True),
        # Exchange-listed (after normalization) → YFinanceProvider
        ("159501", False),  # normalizes to 159501.SZ
        ("510310", False),  # normalizes to 510310.SS
        ("0700.HK", False),
        ("AAPL", False),
        ("TEC.TO", False),
        ("BTC-USD", False),
    ],
)
def test_quote_service_routes_to_correct_provider(db, symbol, is_cn_fund):
    """QuoteService routes each holding symbol to the expected provider type."""
    live_data = {"price": 99.9, "prev_close": 98.0, "currency": "USD"}
    cn_provider = _mock_provider(
        supports=is_cn_fund, live_data=live_data if is_cn_fund else {}
    )
    yf_provider = _mock_provider(
        supports=not is_cn_fund, live_data=live_data if not is_cn_fund else {}
    )

    result = QuoteService(db, [cn_provider, yf_provider]).get_quote(symbol)

    if is_cn_fund:
        cn_provider.fetch_live.assert_called_once()
        yf_provider.fetch_live.assert_not_called()
    else:
        yf_provider.fetch_live.assert_called_once()
        cn_provider.fetch_live.assert_not_called()

    assert result is not None
    assert result["price"] == pytest.approx(99.9)


# ── QuoteService.get_quote ────────────────────────────────────────────────────


def test_get_quote_returns_none_when_no_data_and_live_fails(db):
    provider = _mock_provider(live_data={})
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result is None


def test_get_quote_reads_from_db_when_fresh(db):
    _seed_stock(db, "AAPL", price=150.0, age_seconds=10)
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
    _seed_stock(db, "AAPL", price=150.0, prev_close=100.0, age_seconds=10)
    provider = _mock_provider()
    result = QuoteService(db, [provider]).get_quote("AAPL")
    assert result["change_pct"] == pytest.approx(50.0)


def test_get_quote_normalizes_symbol(db):
    _seed_stock(db, "^GSPC", price=5000.0, age_seconds=10)
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


def _seed_stock_no_price(db, symbol, prev_close=481.6, currency="HKD"):
    """Seed a stock with only prev_close (price=NULL) — simulates NaN-poisoned DB row."""
    repo = StockSQLiteRepository(db)
    stock = repo.upsert(symbol, {"prev_close": prev_close, "currency": currency})
    stock.updated_at = datetime.utcnow() - timedelta(seconds=400)
    db.commit()
    return stock


def test_get_quote_uses_prev_close_when_db_price_null_and_live_fails(db):
    # Regression: 0700.HK showed $0 / -100% when yfinance returned NaN close
    # and poisoned the DB with NULL price but valid prev_close.
    _seed_stock_no_price(db, "0700.HK", prev_close=481.6)
    provider = _mock_provider(live_data={})
    result = QuoteService(db, [provider]).get_quote("0700.HK")
    assert result is not None
    assert result["price"] == pytest.approx(481.6)


def test_get_quote_returns_none_when_price_and_prev_close_both_null_and_live_fails(db):
    repo = StockSQLiteRepository(db)
    stock = repo.upsert("NEWSTOCK", {"currency": "USD"})
    stock.updated_at = datetime.utcnow() - timedelta(seconds=400)
    db.commit()
    provider = _mock_provider(live_data={})
    result = QuoteService(db, [provider]).get_quote("NEWSTOCK")
    assert result is None


# ── QuoteService.get_full_quote ───────────────────────────────────────────────


def test_get_full_quote_delegates_to_provider(db):
    full_data = {"price": 150.0, "prev_close": 148.0, "name": "Apple", "pe_ttm": 28.5}
    provider = _mock_provider(full_data=full_data)
    result = QuoteService(db, [provider]).get_full_quote("AAPL")
    assert result["pe_ttm"] == 28.5
    provider.fetch_full.assert_called_once_with("AAPL")


def test_get_full_quote_returns_empty_when_no_provider_supports(db):
    provider = _mock_provider(supports=False)
    result = QuoteService(db, [provider]).get_full_quote("AAPL")
    assert result == {}


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
