"""Background alert scheduler for packaged (frozen) app mode.

Runs run_check() on a repeating timer. The scheduler only starts when
sys.frozen is True — script-based users continue using cron.
"""

import logging
import threading

from fin.config import APP_CONFIG
from fin.services.alert_checker import run_check

logger = logging.getLogger(__name__)

ALERT_INTERVAL_SECONDS: int = APP_CONFIG.get("alert_check_interval_seconds", 1200)


def _scheduler_loop(stop_event: threading.Event) -> None:
    """Run run_check() every ALERT_INTERVAL_SECONDS until stop_event is set."""
    while not stop_event.wait(timeout=ALERT_INTERVAL_SECONDS):
        try:
            logger.info("Running scheduled alert check")
            run_check()
        except Exception:
            logger.exception("Alert scheduler: run_check() failed")


def start_alert_scheduler() -> threading.Event:
    """Start the alert scheduler background thread.

    Returns:
        stop_event: Pass to stop_alert_scheduler() to halt the thread.
    """
    stop_event = threading.Event()
    t = threading.Thread(
        target=_scheduler_loop,
        args=(stop_event,),
        daemon=True,
        name="alert-scheduler",
    )
    t.start()
    return stop_event


def stop_alert_scheduler(stop_event: threading.Event) -> None:
    """Signal the scheduler thread to stop."""
    stop_event.set()
