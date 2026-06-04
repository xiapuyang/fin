"""Background benchmark scheduler for packaged (frozen) app mode.

Fires on the hour (aligned to HH:00:00 UTC) and computes benchmark results
for all benchmark-enabled accounts that do not yet have today's result.
Only starts when sys.frozen is True — dev users trigger computation via
the frontend or POST /api/benchmark/compute/{id}.
"""

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _seconds_until_next_hour() -> float:
    """Return seconds from now until the next HH:00:00 UTC (minimum 1 second)."""
    now = datetime.now(timezone.utc)
    elapsed = now.minute * 60 + now.second
    remaining = 3600 - elapsed
    return max(remaining, 1)


def _run_once() -> None:
    """Compute benchmark results for all eligible accounts."""
    from fin.database import SessionLocal
    from fin.models.account import AccountModel
    from fin.models.benchmark_result import BenchmarkResultModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import compute as benchmark_compute

    today = str(datetime.now(timezone.utc).date())
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
            already_done = (
                db.query(BenchmarkResultModel)
                .filter(
                    BenchmarkResultModel.account_id == account.id,
                    BenchmarkResultModel.computed_date == today,
                )
                .first()
            )
            if already_done:
                logger.debug(
                    "Benchmark already computed today for account %s", account.id
                )
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


def _scheduler_loop(stop_event: threading.Event) -> None:
    """Sleep until the next hour boundary, then run, then repeat every hour."""
    while not stop_event.wait(timeout=_seconds_until_next_hour()):
        try:
            logger.info("Benchmark scheduler: hourly tick")
            _run_once()
        except Exception:
            logger.exception("Benchmark scheduler: unexpected error in loop")


def start_benchmark_scheduler() -> threading.Event:
    """Start the benchmark scheduler background thread.

    Returns:
        stop_event: Pass to stop_benchmark_scheduler() to halt the thread.
    """
    stop_event = threading.Event()
    t = threading.Thread(
        target=_scheduler_loop,
        args=(stop_event,),
        daemon=True,
        name="benchmark-scheduler",
    )
    t.start()
    return stop_event


def stop_benchmark_scheduler(stop_event: threading.Event) -> None:
    """Signal the benchmark scheduler thread to stop."""
    stop_event.set()
