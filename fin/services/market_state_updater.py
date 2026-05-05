"""Background service: compute market open/close state every 5 minutes.

Uses exchange_calendars (authoritative holiday + session data) rather than
yfinance market_state, which is unreliable and a side-effect of price fetching.

US extended-hours windows (PRE/POST) are not exchange-defined; the offsets
below match standard brokerage extended-hours windows.
"""

import json
import logging
import threading
import time

import exchange_calendars as xcals
import pandas as pd

from fin.config import MARKET_STATE_PATH

logger = logging.getLogger(__name__)

UPDATE_INTERVAL = 300  # 5 minutes

_CALENDARS = {
    "US": xcals.get_calendar("XNYS"),
    "HK": xcals.get_calendar("XHKG"),
    "CN": xcals.get_calendar("XSHG"),
}

_US_PRE_OFFSET = pd.Timedelta(hours=5, minutes=30)  # open − 5h30m = 4:00 AM EDT
_US_POST_OFFSET = pd.Timedelta(hours=4)  # close + 4h = 8:00 PM EDT


def _us_state(now: pd.Timestamp) -> str:
    cal = _CALENDARS["US"]
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


def _simple_state(market: str, now: pd.Timestamp) -> str:
    try:
        return "REGULAR" if _CALENDARS[market].is_open_on_minute(now) else "CLOSED"
    except Exception:
        return "CLOSED"


def compute_and_write() -> None:
    now = pd.Timestamp.now(tz="UTC")
    states = {
        "US": _us_state(now),
        "HK": _simple_state("HK", now),
        "CN": _simple_state("CN", now),
        "updated_at": now.isoformat(),
    }
    MARKET_STATE_PATH.write_text(json.dumps(states))
    logger.info(
        "market states: US=%s HK=%s CN=%s", states["US"], states["HK"], states["CN"]
    )


def _loop() -> None:
    while True:
        try:
            compute_and_write()
        except Exception:
            logger.exception("market state update failed")
        time.sleep(UPDATE_INTERVAL)


def start_market_state_updater() -> threading.Thread:
    t = threading.Thread(target=_loop, daemon=True, name="market-state-updater")
    t.start()
    logger.info("Market state updater started (interval=%ds)", UPDATE_INTERVAL)
    return t
