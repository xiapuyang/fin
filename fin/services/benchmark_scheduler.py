"""Background benchmark scheduler.

Two jobs run in daemon threads:
1. Hourly compute: fires at each HH:00 UTC, recomputes live XIRR for all
   benchmark-enabled accounts that don't have a fresh result.
2. Startup + nightly backfill: runs once shortly after server start, then
   nightly at 06:00 UTC, filling historical benchmark_results for all past
   trading dates.

In frozen (packaged) mode both jobs are started automatically. In dev mode
only the backfill thread starts (so history is available without manual
triggers), while the hourly compute is triggered from the frontend.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _seconds_until_next_hour() -> float:
    """Return seconds from now until the next HH:00:00 UTC (minimum 1 second)."""
    now = datetime.now(timezone.utc)
    elapsed = now.minute * 60 + now.second
    return max(3600 - elapsed, 1)


def _seconds_until_next_6am_utc() -> float:
    """Return seconds until next 06:00 UTC (minimum 60 s)."""
    now = datetime.now(timezone.utc)
    today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
    target = today_6am if now < today_6am else today_6am + timedelta(days=1)
    return max((target - now).total_seconds(), 60)


# ── Hourly compute ────────────────────────────────────────────────────────────


def _run_compute_once() -> None:
    from fin.database import SessionLocal
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import (
        compute as benchmark_compute,
        has_recent_result,
    )

    db = SessionLocal()
    try:
        accounts = (
            db.query(AccountModel)
            .filter(
                AccountModel.user_id == MOCK_USER_ID,
                AccountModel.benchmark_enabled == "1",
            )
            .all()
        )
        logger.info(
            "Benchmark scheduler: checking %d enabled account(s)", len(accounts)
        )
        for account in accounts:
            if has_recent_result(db, account.id):
                logger.debug("Benchmark already fresh for account %s", account.id)
                continue
            try:
                benchmark_compute(db, account.id)
                logger.info(
                    "Benchmark computed for account %s (%s)", account.id, account.name
                )
            except Exception:
                logger.exception(
                    "Benchmark scheduler: compute failed for account %s", account.id
                )
    finally:
        db.close()


def _compute_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(timeout=_seconds_until_next_hour()):
        try:
            logger.info("Benchmark scheduler: hourly tick")
            _run_compute_once()
        except Exception:
            logger.exception("Benchmark scheduler: unexpected error in compute loop")


# ── Backfill ──────────────────────────────────────────────────────────────────


def _run_backfill_once() -> None:
    from fin.database import SessionLocal
    from fin.services.benchmark_history_service import backfill_all

    db = SessionLocal()
    try:
        backfill_all(db)
    except Exception:
        logger.exception("Benchmark backfill: unexpected error")
    finally:
        db.close()


def _backfill_loop(stop_event: threading.Event) -> None:
    # Run immediately at startup (short delay for DB to settle)
    stop_event.wait(timeout=5)
    if stop_event.is_set():
        return
    try:
        logger.info("Benchmark backfill: startup run")
        _run_backfill_once()
    except Exception:
        logger.exception("Benchmark backfill: startup run failed")

    # Then every hour at HH:00 UTC
    while not stop_event.wait(timeout=_seconds_until_next_hour()):
        try:
            logger.info("Benchmark backfill: hourly run")
            _run_backfill_once()
        except Exception:
            logger.exception("Benchmark backfill: hourly run failed")


# ── Public API ────────────────────────────────────────────────────────────────


def start_benchmark_scheduler() -> threading.Event:
    """Start hourly compute scheduler (frozen/packaged mode only)."""
    stop_event = threading.Event()
    t = threading.Thread(
        target=_compute_loop,
        args=(stop_event,),
        daemon=True,
        name="benchmark-scheduler",
    )
    t.start()
    return stop_event


def stop_benchmark_scheduler(stop_event: threading.Event) -> None:
    stop_event.set()


def start_benchmark_backfill() -> threading.Event:
    """Start the backfill thread (runs in both dev and frozen mode)."""
    stop_event = threading.Event()
    t = threading.Thread(
        target=_backfill_loop,
        args=(stop_event,),
        daemon=True,
        name="benchmark-backfill",
    )
    t.start()
    return stop_event


def stop_benchmark_backfill(stop_event: threading.Event) -> None:
    stop_event.set()
