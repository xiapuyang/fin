#!/usr/bin/env python3
"""Cron entry point: check stock alerts and send email notifications."""

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json

from agentmail import AgentMail

from fin.alert_email import build_summary_email
from fin.config import AGENTMAIL_API_KEY, AGENTMAIL_INBOX, LAST_CHECK_PATH
from fin.database import SessionLocal, init_db
from fin.logger import setup_logging
from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin.services.providers import build_default_providers
from fin.services.quote import QuoteService
from fin import settings as settings_store

VALID_CONDITIONS = {"price_gte", "price_lte", "change_gte", "change_lte"}

setup_logging("check-alerts")
logger = logging.getLogger(__name__)


def _get_agentmail_client() -> AgentMail | None:
    if not AGENTMAIL_API_KEY:
        return None
    return AgentMail(api_key=AGENTMAIL_API_KEY)


def _send_email(
    am: AgentMail, subject: str, html_body: str, text_body: str, notify_email: str
) -> None:
    if not AGENTMAIL_INBOX:
        logger.warning("FIN_AGENTMAIL_INBOX not set; skipping email send")
        return
    am.inboxes.messages.send(
        inbox_id=AGENTMAIL_INBOX,
        to=notify_email,
        subject=subject,
        text=text_body,
        html=html_body,
    )


def _check_condition(
    condition: str, value: float, price: float, change_pct: float
) -> bool:
    if condition == "price_gte":
        return price >= value
    if condition == "price_lte":
        return price <= value
    if condition == "change_gte":
        return change_pct >= value
    if condition == "change_lte":
        return change_pct <= value
    return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true", help="Skip market-state check (for testing)"
    )
    args = parser.parse_args()

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
            logger.info("No enabled alerts, exiting")
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
        price_data: dict[str, tuple[float, float]] = {}
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
                # None market_state means the provider has no session concept (e.g. CN funds).
                if (
                    not args.force
                    and market_state is not None
                    and market_state != "REGULAR"
                ):
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

            if not _check_condition(alert.condition, alert.value, price, change_pct):
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


if __name__ == "__main__":
    main()
