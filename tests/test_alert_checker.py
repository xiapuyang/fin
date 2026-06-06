"""Tests for fin/services/alert_checker.py."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.database import Base, import_all_models
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin.schemas.alert import AlertCreate
from fin.services.alert_checker import _exclusive_lock, check_condition, run_check

_MOD = "fin.services.alert_checker"


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


# ── check_condition ───────────────────────────────────────────────────────────


def test_check_condition_price_gte_triggered():
    assert check_condition("price_gte", 100.0, 110.0, 0.0)


def test_check_condition_price_gte_not_triggered():
    assert not check_condition("price_gte", 100.0, 90.0, 0.0)


def test_check_condition_price_lte_triggered():
    assert check_condition("price_lte", 100.0, 90.0, 0.0)


def test_check_condition_price_lte_not_triggered():
    assert not check_condition("price_lte", 100.0, 110.0, 0.0)


def test_check_condition_change_gte_triggered():
    assert check_condition("change_gte", 5.0, 0.0, 6.0)


def test_check_condition_change_lte_triggered():
    assert check_condition("change_lte", -3.0, 0.0, -4.0)


def test_check_condition_unknown_returns_false():
    assert not check_condition("unknown_op", 100.0, 200.0, 50.0)


def test_check_condition_price_gte_at_boundary():
    assert check_condition("price_gte", 100.0, 100.0, 0.0)


def test_check_condition_price_lte_at_boundary():
    assert check_condition("price_lte", 100.0, 100.0, 0.0)


# ── run_check ─────────────────────────────────────────────────────────────────


def _run_with_quote(
    db, quote, alert_condition="price_lte", alert_value=200.0, force=False
):
    """Call run_check() with full patch set; return list of fired alert IDs."""
    from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository

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
        run_check(force=force)

    return fired_ids


def _make_quote(price, change_pct, market_state):
    return {
        "price": price,
        "prev_close": price / (1 + change_pct / 100),
        "change_pct": change_pct,
        "market_state": market_state,
    }


def test_run_check_no_alerts_returns_without_error(db):
    """run_check with no enabled alerts completes without error."""
    with (
        patch.dict(
            "os.environ",
            {"AGENTMAIL_API_KEY": "test-key", "FIN_AGENTMAIL_INBOX": "test-inbox"},
        ),
        patch(f"{_MOD}.SessionLocal", return_value=db),
        patch(f"{_MOD}.init_db"),
        patch(f"{_MOD}.AlertSQLiteRepository") as mock_repo_cls,
        patch(
            f"{_MOD}.settings_store.load",
            return_value={"notify_email": "", "notify_enabled": False},
        ),
    ):
        mock_repo = MagicMock()
        mock_repo.get_enabled.return_value = []
        mock_repo_cls.return_value = mock_repo
        run_check()  # should not raise


def test_run_check_fires_matching_alert(db):
    quote = _make_quote(price=100.0, change_pct=2.0, market_state="REGULAR")
    fired = _run_with_quote(db, quote, alert_condition="price_lte", alert_value=150.0)
    assert len(fired) == 1


def test_run_check_does_not_fire_non_matching_alert(db):
    quote = _make_quote(price=200.0, change_pct=2.0, market_state="REGULAR")
    fired = _run_with_quote(db, quote, alert_condition="price_lte", alert_value=150.0)
    assert len(fired) == 0


def test_run_check_skips_non_regular_market_state(db):
    quote = _make_quote(price=100.0, change_pct=2.0, market_state="PRE")
    fired = _run_with_quote(db, quote, alert_condition="price_lte", alert_value=150.0)
    assert len(fired) == 0


def test_run_check_force_bypasses_market_state(db):
    quote = _make_quote(price=100.0, change_pct=2.0, market_state="PRE")
    fired = _run_with_quote(
        db, quote, alert_condition="price_lte", alert_value=150.0, force=True
    )
    assert len(fired) == 1


def test_run_check_continues_after_single_symbol_exception(db):
    """An exception fetching one symbol does not abort the whole check."""
    from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository

    alert_repo = AlertSQLiteRepository(db)
    alert_repo.create(
        AlertCreate(symbol="FAIL", name="will-fail", condition="price_lte", value=999.0)
    )
    alert_repo.create(
        AlertCreate(symbol="AAPL", name="will-fire", condition="price_lte", value=999.0)
    )
    fire_repo = AlertFireSQLiteRepository(db)

    good_quote = _make_quote(price=100.0, change_pct=0.0, market_state="REGULAR")

    def side_effect(symbol):
        if symbol == "FAIL":
            raise RuntimeError("network error")
        return good_quote

    mock_qs = MagicMock()
    mock_qs.get_quote.side_effect = side_effect

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
        run_check(force=True)

    assert len(fired_ids) == 1  # AAPL fired despite FAIL raising


def test_run_check_does_not_start_scheduler_in_script_mode():
    """The scheduler thread is NOT started by run_check() itself."""
    import threading

    before = {t.name for t in threading.enumerate()}
    with (
        patch(f"{_MOD}.SessionLocal"),
        patch(f"{_MOD}.init_db"),
        patch(f"{_MOD}.AlertSQLiteRepository") as mock_repo_cls,
        patch(
            f"{_MOD}.settings_store.load",
            return_value={"notify_email": "", "notify_enabled": False},
        ),
    ):
        mock_repo = MagicMock()
        mock_repo.get_enabled.return_value = []
        mock_repo_cls.return_value = mock_repo
        run_check()
    after = {t.name for t in threading.enumerate()}
    assert "alert-scheduler" not in (after - before)


# ── scheduler integration (frozen mode) ──────────────────────────────────────


def test_scheduler_starts_in_frozen_mode():
    """In frozen mode the lifespan should start the alert-scheduler thread."""
    import threading

    from fin.services.alert_scheduler import start_alert_scheduler, stop_alert_scheduler

    stop_event = start_alert_scheduler()
    try:
        names = {t.name for t in threading.enumerate()}
        assert "alert-scheduler" in names
    finally:
        stop_alert_scheduler(stop_event)


def test_scheduler_stops_cleanly():
    """stop_alert_scheduler sets the stop event so the thread exits."""

    from fin.services.alert_scheduler import start_alert_scheduler, stop_alert_scheduler

    stop_event = start_alert_scheduler()
    stop_alert_scheduler(stop_event)
    assert stop_event.is_set()


# ── _exclusive_lock ───────────────────────────────────────────────────────────


def test_exclusive_lock_raises_runtime_error_on_contention(tmp_path):
    pytest.importorskip("fcntl")
    lock_path = tmp_path / "test.lock"
    with (
        patch(f"{_MOD}.ALERT_LOCK_PATH", lock_path),
        patch("fcntl.flock", side_effect=OSError("already locked")),
    ):
        with pytest.raises(RuntimeError, match="lock held"):
            with _exclusive_lock():
                pass


def test_run_check_skips_when_lock_held(db):
    """Second caller returns immediately without invoking _run_check_inner."""
    with (
        patch(f"{_MOD}._exclusive_lock", side_effect=RuntimeError("lock held")),
        patch(f"{_MOD}._run_check_inner") as mock_inner,
    ):
        run_check()
        mock_inner.assert_not_called()


# ── alert_scheduler ───────────────────────────────────────────────────────────


def test_alert_scheduler_stop_event_halts_loop():
    import threading
    from fin.services.alert_scheduler import _scheduler_loop

    stop = threading.Event()
    stop.set()  # set immediately so loop exits right away
    _scheduler_loop(stop)  # should return without calling run_check


def test_alert_scheduler_run_check_called(monkeypatch):
    import threading
    from fin.services import alert_scheduler

    calls = []
    monkeypatch.setattr(alert_scheduler, "run_check", lambda: calls.append(1))
    monkeypatch.setattr(alert_scheduler, "ALERT_INTERVAL_SECONDS", 0)

    stop = threading.Event()
    t = threading.Thread(
        target=alert_scheduler._scheduler_loop, args=(stop,), daemon=True
    )
    t.start()
    import time

    time.sleep(0.05)
    stop.set()
    t.join(timeout=1)
    assert len(calls) >= 1


def test_start_and_stop_alert_scheduler():
    from fin.services.alert_scheduler import start_alert_scheduler, stop_alert_scheduler
    from unittest.mock import patch

    with patch("fin.services.alert_scheduler.run_check"):
        stop_event = start_alert_scheduler()
        assert not stop_event.is_set()
        stop_alert_scheduler(stop_event)
        assert stop_event.is_set()
