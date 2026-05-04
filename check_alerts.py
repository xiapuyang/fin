#!/usr/bin/env python3
"""Cron entry point: check stock alerts and send email notifications."""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yfinance as yf
from agentmail import AgentMail

from fin.database import SessionLocal, init_db
from fin.logger import setup_logging
from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin import settings as settings_store

AGENTMAIL_INBOX = "agent_of_sharp@agentmail.to"

VALID_CONDITIONS = {"price_gte", "price_lte", "change_gte", "change_lte"}

setup_logging("check-alerts")
logger = logging.getLogger(__name__)


def _get_agentmail_client() -> AgentMail | None:
    key = os.environ.get("AGENTMAIL_API_KEY", "")
    if not key:
        return None
    return AgentMail(api_key=key)


def _send_email(
    am: AgentMail, subject: str, html_body: str, text_body: str, notify_email: str
) -> None:
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


def _build_summary_email(fired: list[tuple]) -> tuple[str, str, str]:
    cond_labels = {
        "price_gte": "价格 ≥",
        "price_lte": "价格 ≤",
        "change_gte": "涨幅 ≥",
        "change_lte": "跌幅 ≤",
    }

    if len(fired) == 1:
        alert, _, _ = fired[0]
        subject = f"[fin] 提醒触发: {alert.name} ({alert.symbol})"
    else:
        subject = f"[fin] {len(fired)} 个提醒触发"

    rows_html = ""
    rows_text = ""
    for alert, price, change_pct in fired:
        change_str = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
        color = "#D9352B" if change_pct >= 0 else "#1F8A4C"
        label = cond_labels.get(alert.condition, alert.condition)
        cond_str = f"{label} {alert.value}{'%' if 'change' in alert.condition else ''}"
        rows_html += (
            f"<tr>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-weight:600'>{alert.name}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;color:#5C6270'>{alert.symbol}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5'>{cond_str}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;font-weight:600'>{price:.2f}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;color:{color};font-weight:600'>{change_str}</td>"
            f"</tr>"
        )
        rows_text += f"• {alert.name} ({alert.symbol}): {cond_str}  价格={price:.2f}  涨跌={change_str}\n"

    html_body = (
        f"<html><body style='font-family:sans-serif;color:#14161B;max-width:600px'>"
        f"<h2 style='margin-bottom:4px'>📊 股票提醒触发</h2>"
        f"<p style='color:#5C6270;margin-top:0'>fin · {len(fired)} 个提醒已触发</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>"
        f"<thead><tr style='color:#5C6270;font-size:12px'>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>名称</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>代码</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>条件</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>价格</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>涨跌</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>"
        f"<p style='font-size:12px;color:#8B8F9A;margin-top:16px'>以上提醒已自动禁用，请前往 fin 管理页面重新启用。</p>"
        f"</body></html>"
    )
    text_body = f"触发 {len(fired)} 个提醒:\n\n{rows_text}\n以上提醒已自动禁用。"

    return subject, html_body, text_body


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

        price_data: dict[str, tuple[float, float]] = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.fast_info
                if not args.force and getattr(info, "market_state", None) != "REGULAR":
                    logger.info(
                        "Market not REGULAR for %s (state=%s), skipping",
                        symbol,
                        getattr(info, "market_state", "?"),
                    )
                    price_data[symbol] = (None, None)
                    continue
                price = info.last_price
                prev_close = info.previous_close
                if price is None or prev_close is None or prev_close == 0:
                    logger.warning("Missing price data for %s", symbol)
                    price_data[symbol] = (None, None)
                    continue
                change_pct = (price - prev_close) / prev_close * 100
                price_data[symbol] = (price, change_pct)
                logger.info("%s: price=%.4g change=%.2f%%", symbol, price, change_pct)
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
            fired.append((alert, price, change_pct))

            try:
                fire_repo.create(alert.id, price, change_pct)
                alert_repo.disable(alert.id)
                logger.info("Alert %s disabled after fire", alert.id)
            except Exception:
                logger.exception("Failed to record fire for alert %s", alert.id)

        if fired and am:
            try:
                subject, html_body, text_body = _build_summary_email(fired)
                _send_email(am, subject, html_body, text_body, notify_email)
                logger.info("Summary email sent for %d alert(s)", len(fired))
            except Exception:
                logger.exception("Failed to send summary email")

    finally:
        db.close()


if __name__ == "__main__":
    main()
