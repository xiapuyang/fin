#!/usr/bin/env python3
"""End-to-end verification of the alert notification pipeline.

Checks each link of the chain that fires a real alert email:
  [1] .env credentials (AGENTMAIL_API_KEY, FIN_AGENTMAIL_INBOX)
  [2] data/settings.json (notify_email, notify_enabled)
  [3] SQLite DB (init_db, alert & fire tables readable)
  [4] crontab entry for check_alerts.py
  [5] Send the real triggered-alert email template with synthetic data,
      so you can preview exactly what a fired alert looks like.

Usage:
    uv run python verify_email.py              # send to settings.notify_email
    uv run python verify_email.py --to a@b.com # override recipient
    uv run python verify_email.py --no-send    # run checks only, skip email
"""

import argparse
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))

from agentmail import AgentMail

from fin import settings as settings_store
from fin.alert_email import build_summary_email
from fin.config import AGENTMAIL_API_KEY, AGENTMAIL_INBOX
from fin.database import SessionLocal, init_db
from fin.logger import setup_logging
from fin.models.alert import AlertFireModel
from fin.repositories.alert_sqlite import AlertSQLiteRepository

setup_logging("verify-email")
logger = logging.getLogger(__name__)

PASS = "\033[32mPASS\033[0m"
WARN = "\033[33mWARN\033[0m"
FAIL = "\033[31mFAIL\033[0m"


class Result:
    """Accumulates checklist results — FAIL blocks, WARN does not."""

    def __init__(self) -> None:
        self.failed = False
        self.warned = False

    def ok(self, step: str, detail: str = "") -> None:
        print(f"[{PASS}] {step}" + (f" — {detail}" if detail else ""))

    def warn(self, step: str, detail: str) -> None:
        self.warned = True
        print(f"[{WARN}] {step} — {detail}")

    def fail(self, step: str, detail: str) -> None:
        self.failed = True
        print(f"[{FAIL}] {step} — {detail}")


def check_env(r: Result) -> bool:
    """Verify .env credentials. Returns True if both present."""
    if not AGENTMAIL_API_KEY:
        r.fail("[1] .env", "AGENTMAIL_API_KEY not set")
    if not AGENTMAIL_INBOX:
        r.fail("[1] .env", "FIN_AGENTMAIL_INBOX not set")
    if AGENTMAIL_API_KEY and AGENTMAIL_INBOX:
        r.ok("[1] .env", f"inbox={AGENTMAIL_INBOX}")
        return True
    return False


def check_settings(r: Result, override_to: str | None) -> str | None:
    """Verify settings.json. Returns recipient or None."""
    settings = settings_store.load()
    notify_email = override_to or settings.get("notify_email", "")
    notify_enabled = settings.get("notify_enabled", True)

    if not notify_email:
        r.fail(
            "[2] settings.json",
            "no notify_email — set in TopBar → 应用设置, or pass --to",
        )
        return None
    if not notify_enabled and not override_to:
        r.warn(
            "[2] settings.json",
            f"notify_enabled=false → cron would skip; recipient={notify_email}",
        )
    else:
        r.ok("[2] settings.json", f"recipient={notify_email}")
    return notify_email


def check_db(r: Result) -> None:
    """Verify DB initialization and alert/fire repositories are readable."""
    try:
        init_db()
        db = SessionLocal()
        try:
            enabled = len(AlertSQLiteRepository(db).get_enabled())
            fire_count = db.query(AlertFireModel).count()
        finally:
            db.close()
    except Exception as exc:
        r.fail("[3] DB", f"{type(exc).__name__}: {exc}")
        return
    r.ok("[3] DB", f"enabled_alerts={enabled}, total_fires={fire_count}")


def check_crontab(r: Result) -> None:
    """Look for a crontab line referencing check_alerts.py in this project."""
    project_dir = Path(__file__).parent.resolve()
    try:
        proc = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5
        )
    except FileNotFoundError:
        r.warn("[4] crontab", "crontab command not found")
        return
    except subprocess.TimeoutExpired:
        r.warn("[4] crontab", "crontab -l timed out")
        return

    if proc.returncode != 0:
        r.warn("[4] crontab", "no crontab installed for current user")
        return

    matches = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "check_alerts.py" in line and not line.strip().startswith("#")
    ]
    if not matches:
        r.warn(
            "[4] crontab",
            "no entry references check_alerts.py (alerts will not fire automatically)",
        )
        return

    in_project = [m for m in matches if str(project_dir) in m]
    if not in_project:
        r.warn(
            "[4] crontab",
            f"found check_alerts.py entry but not in {project_dir}: {matches[0]}",
        )
        return

    schedule = " ".join(in_project[0].split()[:5])
    r.ok("[4] crontab", f"schedule='{schedule}'")


def send_preview(r: Result, recipient: str) -> None:
    """Send the real triggered-alert template populated with synthetic data."""
    ts = datetime.now().isoformat(timespec="seconds")
    fired = [
        (
            SimpleNamespace(
                name="Apple", symbol="AAPL", condition="price_gte", value=200.0
            ),
            204.37,
            2.18,
        ),
        (
            SimpleNamespace(
                name="腾讯", symbol="0700.HK", condition="change_lte", value=-3.0
            ),
            378.20,
            -3.45,
        ),
    ]
    subject, html_body, text_body = build_summary_email(fired)
    subject = f"{subject} · verify {ts}"

    try:
        am = AgentMail(api_key=AGENTMAIL_API_KEY)
        result = am.inboxes.messages.send(
            inbox_id=AGENTMAIL_INBOX,
            to=recipient,
            subject=subject,
            text=text_body,
            html=html_body,
        )
    except Exception as exc:
        logger.exception("AgentMail send failed")
        r.fail("[5] send preview", f"{type(exc).__name__}: {exc}")
        return

    msg_id = getattr(result, "message_id", None) or getattr(result, "id", None)
    r.ok("[5] send preview", f"id={msg_id or '?'}")
    print(f"        recipient: {recipient}")
    print(f"        subject:   {subject}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", help="Override recipient address")
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Run checks only, skip the preview email send",
    )
    args = parser.parse_args()

    r = Result()
    print("fin · alert notification pipeline verification")
    print("-" * 60)

    env_ok = check_env(r)
    recipient = check_settings(r, args.to)
    check_db(r)
    check_crontab(r)

    if args.no_send:
        print("[--] [5] send preview — skipped (--no-send)")
    elif env_ok and recipient:
        send_preview(r, recipient)
    else:
        r.fail("[5] send preview", "skipped (.env or settings.json failed)")

    print("-" * 60)
    if r.failed:
        print("Result: FAIL — pipeline is broken")
        return 1
    if r.warned:
        print("Result: PASS with warnings — review above")
        return 0
    print("Result: PASS — pipeline is healthy end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
