"""Background service: compute market open/close state every 5 minutes.

Uses exchange_calendars (authoritative holiday + session data) rather than
yfinance market_state, which is unreliable and a side-effect of price fetching.

US/CA extended-hours windows (PRE/POST) are not exchange-defined; the offsets
below match standard brokerage extended-hours windows.
"""

import json
import logging
import threading
import time
from datetime import timedelta

from fin.config import MARKET_STATE_PATH

logger = logging.getLogger(__name__)

UPDATE_INTERVAL: int = 300  # 5 minutes

_CALENDARS: dict | None = None
_write_lock = threading.Lock()

_US_PRE_OFFSET = timedelta(hours=5, minutes=30)  # open − 5h30m = 4:00 AM EDT
_US_POST_OFFSET = timedelta(hours=4)  # close + 4h = 8:00 PM EDT


def _get_calendars() -> dict:
    """Return exchange calendar instances, initializing lazily on first call."""
    global _CALENDARS
    if _CALENDARS is None:
        import exchange_calendars as xcals

        _CALENDARS = {
            "US": xcals.get_calendar("XNYS"),
            "HK": xcals.get_calendar("XHKG"),
            "CN": xcals.get_calendar("XSHG"),
            "CA": xcals.get_calendar("XTSE"),
        }
    return _CALENDARS


def _et_state(market: str, now) -> str:
    """Return ET-style market state (CLOSED/PRE/REGULAR/POST) for an Eastern Time exchange."""
    cal = _get_calendars()[market]
    try:
        if not cal.is_session(now.date()):
            return "CLOSED"
        session = cal.date_to_session(now.date(), direction="next")
        reg_open = cal.session_open(session)
        reg_close = cal.session_close(session)
    except Exception:
        return "CLOSED"
    if now < reg_open - _US_PRE_OFFSET or now >= reg_close + _US_POST_OFFSET:
        return "CLOSED"
    if now < reg_open:
        return "PRE"
    if now < reg_close:
        return "REGULAR"
    return "POST"


def _simple_state(market: str, now) -> str:
    """Return REGULAR if the given market is open at now, else CLOSED."""
    try:
        return (
            "REGULAR" if _get_calendars()[market].is_open_on_minute(now) else "CLOSED"
        )
    except Exception:
        return "CLOSED"


def compute_and_write() -> None:
    """Compute current market states and write them atomically to MARKET_STATE_PATH."""
    import pandas as pd

    now = pd.Timestamp.now(tz="UTC")
    states = {
        "US": _et_state("US", now),
        "HK": _simple_state("HK", now),
        "CN": _simple_state("CN", now),
        "CA": _et_state("CA", now),
        "updated_at": now.isoformat(),
    }
    with _write_lock:
        tmp = MARKET_STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(states))
        tmp.replace(MARKET_STATE_PATH)
    logger.info(
        "market states: US=%s HK=%s CN=%s CA=%s",
        states["US"],
        states["HK"],
        states["CN"],
        states["CA"],
    )


def _loop() -> None:
    """Run compute_and_write in an infinite loop, sleeping UPDATE_INTERVAL seconds between iterations."""
    while True:
        try:
            compute_and_write()
        except Exception:
            logger.exception("market state update failed")
        time.sleep(UPDATE_INTERVAL)


def start_market_state_updater() -> threading.Thread:
    """Start the background market state updater thread and return it."""
    t = threading.Thread(target=_loop, daemon=True, name="market-state-updater")
    t.start()
    logger.info("Market state updater started (interval=%ds)", UPDATE_INTERVAL)
    return t
