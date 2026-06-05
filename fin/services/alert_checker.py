"""Alert checking service: fetch prices and fire triggered alerts.

This module exists so the core logic can be called from both the background
scheduler (running inside serve.py) and the standalone check_alerts.py cron
script. A file lock at ALERT_LOCK_PATH ensures at most one instance runs at
a time, so both can coexist without duplicating work or double-firing alerts.
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime

from fin.config import ALERT_LOCK_PATH, LAST_CHECK_PATH
from fin.database import SessionLocal, init_db
from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin.services.providers import build_default_providers
from fin.services.quote import QuoteService
from fin import settings as settings_store

logger = logging.getLogger(__name__)

VALID_CONDITIONS = {"price_gte", "price_lte", "change_gte", "change_lte"}


@contextmanager
def _exclusive_lock():
    """Cross-platform exclusive file lock.

    Yields if the lock is acquired. Raises RuntimeError if already held
    by another process (cron job or scheduler instance).
    """
    lock_file = open(ALERT_LOCK_PATH, "a")
    try:
        import fcntl

        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            lock_file.close()
            raise RuntimeError("lock held")
    except OSError:
        lock_file.close()
        raise RuntimeError("lock held")
    try:
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(lock_file, fcntl.LOCK_UN)
        except ImportError:
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        lock_file.close()


def check_condition(
    condition: str, value: float, price: float, change_pct: float
) -> bool:
    """Return True if the alert condition is satisfied."""
    if condition == "price_gte":
        return price >= value
    if condition == "price_lte":
        return price <= value
    if condition == "change_gte":
        return change_pct >= value
    if condition == "change_lte":
        return change_pct <= value
    return False


def _get_agentmail_client():
    key = os.environ.get("AGENTMAIL_API_KEY", "")
    if not key:
        return None
    from agentmail import AgentMail

    return AgentMail(api_key=key)


def _send_email(
    am, subject: str, html_body: str, text_body: str, notify_email: str
) -> None:
    inbox = os.environ.get("FIN_AGENTMAIL_INBOX", "")
    if not inbox:
        logger.warning("FIN_AGENTMAIL_INBOX not set; skipping email send")
        return
    am.inboxes.messages.send(
        inbox_id=inbox,
        to=notify_email,
        subject=subject,
        text=text_body,
        html=html_body,
    )


def run_check(force: bool = False) -> None:
    """Fetch enabled alerts, evaluate conditions, fire matches, send email.

    Acquires an exclusive file lock before running so cron jobs and the
    in-process scheduler cannot execute concurrently. The second caller
    logs a skip message and returns immediately.

    Safe to call repeatedly — creates and closes its own DB session.
    Exceptions are caught per-symbol so one failure doesn't abort the run.

    Returns early without touching the DB when AgentMail is not configured,
    to prevent alerts from firing and disabling themselves without notification.

    Args:
        force: Skip market-state REGULAR check (useful for testing).
    """
    try:
        with _exclusive_lock():
            _run_check_inner(force=force)
    except RuntimeError:
        logger.info(
            "Alert check already running (lock held by another process), skipping"
        )


def _fetch_prices(
    quote_service: QuoteService, symbols: list[str], force: bool
) -> dict[str, tuple[float | None, float | None]]:
    """Fetch current price and change_pct for each symbol.

    Returns a dict mapping symbol to (price, change_pct). Entries are
    (None, None) on fetch failure or when market state is not REGULAR.
    """
    price_data: dict[str, tuple[float | None, float | None]] = {}
    for symbol in symbols:
        try:
            quote = quote_service.get_quote(symbol)
            if (
                not quote
                or quote.get("price") is None
                or quote.get("change_pct") is None
            ):
                logger.warning("Missing price data for %s", symbol)
                price_data[symbol] = (None, None)
                continue
            market_state = quote.get("market_state")
            if not force and market_state is not None and market_state != "REGULAR":
                logger.info(
                    "Market not REGULAR for %s (state=%s), skipping",
                    symbol,
                    market_state,
                )
                price_data[symbol] = (None, None)
                continue
            price_data[symbol] = (quote["price"], quote["change_pct"])
            logger.info(
                "%s: price=%.4g change=%.2f%%",
                symbol,
                quote["price"],
                quote["change_pct"],
            )
        except Exception:
            logger.exception("Failed to fetch %s", symbol)
            price_data[symbol] = (None, None)
    return price_data


def _run_check_inner(force: bool = False) -> None:
    """Core alert check logic — called only when the exclusive lock is held."""
    if not os.environ.get("AGENTMAIL_API_KEY") or not os.environ.get(
        "FIN_AGENTMAIL_INBOX"
    ):
        logger.info(
            "AgentMail not configured (AGENTMAIL_API_KEY / FIN_AGENTMAIL_INBOX); skipping check"
        )
        return

    app_settings = settings_store.load()
    notify_email = app_settings.get("notify_email", "")
    notify_enabled = app_settings.get("notify_enabled", True)

    init_db()
    db = SessionLocal()
    check_completed = False
    try:
        alert_repo = AlertSQLiteRepository(db)
        fire_repo = AlertFireSQLiteRepository(db)
        alerts = alert_repo.get_enabled()

        if not alerts:
            logger.info("No enabled alerts")
            return

        am = _get_agentmail_client()
        if not am:
            logger.warning("AGENTMAIL_API_KEY not set — will check but not send emails")
        if not notify_enabled:
            logger.info("Email notifications disabled in settings")
            am = None
        if not notify_email:
            logger.warning(
                "No notify_email configured — will check but not send emails"
            )
            am = None

        symbols = list({a.symbol for a in alerts})
        logger.info("Fetching data for %d symbols: %s", len(symbols), symbols)

        quote_service = QuoteService(db, build_default_providers())
        price_data = _fetch_prices(quote_service, symbols, force)

        fired: list[tuple] = []
        for alert in alerts:
            price, change_pct = price_data.get(alert.symbol, (None, None))
            if price is None:
                continue

            if alert.condition not in VALID_CONDITIONS:
                logger.warning(
                    "Unknown condition %s for alert %s", alert.condition, alert.id
                )
                continue

            if not check_condition(alert.condition, alert.value, price, change_pct):
                continue

            logger.info(
                "TRIGGERED: %s (%s) — %s %s, price=%.4g change=%.2f%%",
                alert.name,
                alert.symbol,
                alert.condition,
                alert.value,
                price,
                change_pct,
            )
            try:
                fire_repo.create(
                    alert.id, price, change_pct, alert.condition, alert.value
                )
                alert_repo.disable(alert.id)
                fired.append((alert, price, change_pct))
                logger.info("Alert %s disabled after fire", alert.id)
            except Exception:
                logger.exception("Failed to record fire for alert %s", alert.id)

        if fired and am:
            try:
                from fin.alert_email import build_summary_email

                subject, html_body, text_body = build_summary_email(fired)
                _send_email(am, subject, html_body, text_body, notify_email)
                logger.info("Summary email sent for %d alert(s)", len(fired))
            except Exception:
                logger.exception("Failed to send summary email")

        check_completed = True

    finally:
        if check_completed:
            LAST_CHECK_PATH.write_text(
                json.dumps({"checked_at": datetime.utcnow().isoformat() + "Z"})
            )
        db.close()
