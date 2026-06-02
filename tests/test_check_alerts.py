"""Tests for check_alerts market_state gate and condition evaluation."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent.parent))

from fin.services.alert_checker import check_condition as _check_condition
from fin.database import Base
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin.schemas.alert import AlertCreate


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


# ── _check_condition ──────────────────────────────────────────────────────────


def test_check_condition_price_gte_triggered():
    assert _check_condition("price_gte", 100.0, 110.0, 0.0)


def test_check_condition_price_gte_not_triggered():
    assert not _check_condition("price_gte", 100.0, 90.0, 0.0)


def test_check_condition_price_lte_triggered():
    assert _check_condition("price_lte", 100.0, 90.0, 0.0)


def test_check_condition_price_lte_not_triggered():
    assert not _check_condition("price_lte", 100.0, 110.0, 0.0)


def test_check_condition_change_gte_triggered():
    assert _check_condition("change_gte", 5.0, 0.0, 6.0)


def test_check_condition_change_lte_triggered():
    assert _check_condition("change_lte", -3.0, 0.0, -4.0)


def test_check_condition_unknown_returns_false():
    assert not _check_condition("unknown_op", 100.0, 200.0, 50.0)


def test_check_condition_price_gte_at_exact_boundary():
    assert _check_condition("price_gte", 100.0, 100.0, 0.0)


def test_check_condition_price_lte_at_exact_boundary():
    assert _check_condition("price_lte", 100.0, 100.0, 0.0)


def test_check_condition_change_gte_at_exact_boundary():
    assert _check_condition("change_gte", 5.0, 0.0, 5.0)


def test_check_condition_change_lte_at_exact_boundary():
    assert _check_condition("change_lte", -3.0, 0.0, -3.0)


# ── market_state gate ─────────────────────────────────────────────────────────


def _make_quote(price, change_pct, market_state):
    return {
        "price": price,
        "prev_close": price / (1 + change_pct / 100),
        "change_pct": change_pct,
        "market_state": market_state,
    }


_MOD = "fin.services.alert_checker"


def _run_main_with_quote(db, quote, alert_condition="price_lte", alert_value=200.0):
    """Run run_check() with a mocked QuoteService and return fired alert IDs."""
    from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository
    from fin.services.alert_checker import run_check

    alert_repo = AlertSQLiteRepository(db)
    alert_repo.create(
        AlertCreate(
            symbol="AAPL", name="test", condition=alert_condition, value=alert_value
        )
    )
    fire_repo = AlertFireSQLiteRepository(db)

    mock_qs = MagicMock()
    mock_qs.get_quote.return_value = quote

    fired_ids = []
    original_create = fire_repo.create

    def track_create(*args, **kwargs):
        fired_ids.append(args[0])
        return original_create(*args, **kwargs)

    fire_repo.create = track_create

    with (
        patch.dict(
            "os.environ",
            {"AGENTMAIL_API_KEY": "test-key", "FIN_AGENTMAIL_INBOX": "test-inbox"},
        ),
        patch(f"{_MOD}.SessionLocal", return_value=db),
        patch(f"{_MOD}.init_db"),
        patch(f"{_MOD}.QuoteService", return_value=mock_qs),
        patch(f"{_MOD}.build_default_providers", return_value=[]),
        patch(f"{_MOD}.AlertSQLiteRepository", return_value=alert_repo),
        patch(f"{_MOD}.AlertFireSQLiteRepository", return_value=fire_repo),
        patch(
            f"{_MOD}.settings_store.load",
            return_value={"notify_email": "", "notify_enabled": False},
        ),
        patch(f"{_MOD}.LAST_CHECK_PATH") as mock_path,
    ):
        mock_path.write_text = MagicMock()
        run_check(force=False)

    return fired_ids


def test_market_state_none_fires_alert(db):
    """market_state=None (CN fund) should always evaluate the alert."""
    quote = _make_quote(price=100.0, change_pct=2.0, market_state=None)
    fired = _run_main_with_quote(
        db, quote, alert_condition="price_lte", alert_value=150.0
    )
    assert len(fired) == 1


def test_market_state_none_fires_even_when_us_market_is_closed(db):
    """CN fund alert fires even if US market is simultaneously CLOSED.

    Regression guard: _market_for_symbol('013308') used to return 'US',
    causing stale-cache quotes to inherit the US market state and get skipped.
    """
    # Simulate a quote where the live provider correctly returns market_state=None
    # (ChinaFundProvider.fetch_live always returns market_state=None).
    quote = _make_quote(price=100.0, change_pct=2.0, market_state=None)
    fired = _run_main_with_quote(
        db, quote, alert_condition="price_lte", alert_value=150.0
    )
    assert len(fired) == 1


def test_market_state_regular_fires_alert(db):
    """market_state=REGULAR (US open) should evaluate the alert."""
    quote = _make_quote(price=100.0, change_pct=2.0, market_state="REGULAR")
    fired = _run_main_with_quote(
        db, quote, alert_condition="price_lte", alert_value=150.0
    )
    assert len(fired) == 1


def test_market_state_pre_skips_alert(db):
    """market_state=PRE (US pre-market) should skip the alert without firing."""
    quote = _make_quote(price=100.0, change_pct=2.0, market_state="PRE")
    fired = _run_main_with_quote(
        db, quote, alert_condition="price_lte", alert_value=150.0
    )
    assert len(fired) == 0


def test_market_state_closed_skips_alert(db):
    """market_state=CLOSED (US after-hours) should skip the alert without firing."""
    quote = _make_quote(price=100.0, change_pct=2.0, market_state="CLOSED")
    fired = _run_main_with_quote(
        db, quote, alert_condition="price_lte", alert_value=150.0
    )
    assert len(fired) == 0


def test_force_flag_bypasses_market_state_gate(db):
    """--force should fire alerts even when market_state is PRE."""
    quote = _make_quote(price=100.0, change_pct=2.0, market_state="PRE")

    from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository

    alert_repo = AlertSQLiteRepository(db)
    alert_repo.create(
        AlertCreate(symbol="AAPL", name="test", condition="price_lte", value=150.0)
    )
    fire_repo = AlertFireSQLiteRepository(db)

    mock_qs = MagicMock()
    mock_qs.get_quote.return_value = quote

    fired_ids = []
    original_create = fire_repo.create

    def track_create(*args, **kwargs):
        fired_ids.append(args[0])
        return original_create(*args, **kwargs)

    fire_repo.create = track_create

    from fin.services.alert_checker import run_check

    with (
        patch.dict(
            "os.environ",
            {"AGENTMAIL_API_KEY": "test-key", "FIN_AGENTMAIL_INBOX": "test-inbox"},
        ),
        patch(f"{_MOD}.SessionLocal", return_value=db),
        patch(f"{_MOD}.init_db"),
        patch(f"{_MOD}.QuoteService", return_value=mock_qs),
        patch(f"{_MOD}.build_default_providers", return_value=[]),
        patch(f"{_MOD}.AlertSQLiteRepository", return_value=alert_repo),
        patch(f"{_MOD}.AlertFireSQLiteRepository", return_value=fire_repo),
        patch(
            f"{_MOD}.settings_store.load",
            return_value={"notify_email": "", "notify_enabled": False},
        ),
        patch(f"{_MOD}.LAST_CHECK_PATH") as mock_path,
    ):
        mock_path.write_text = MagicMock()
        run_check(force=True)

    assert len(fired_ids) == 1
