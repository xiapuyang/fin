"""Resolve a balance snapshot by date for balance imports.

Pure helpers — AskUserQuestion + decision-to-create live in SKILL.md flow.
"""

import os
import requests


def _fetch_all() -> list[dict]:
    base = os.environ.get("FIN_API_URL", "http://localhost:8899")
    r = requests.get(base + "/api/balance/snapshots", timeout=10)
    r.raise_for_status()
    body = r.json()
    return body if isinstance(body, list) else body.get("items", [])


def find_by_date(date: str) -> dict | None:
    """Return the snapshot record matching snapshot_date, or None."""
    for s in _fetch_all():
        if s.get("snapshot_date") == date:
            return s
    return None


def create(date: str, label: str) -> dict:
    """POST a new snapshot and return the created record (incl. id)."""
    base = os.environ.get("FIN_API_URL", "http://localhost:8899")
    r = requests.post(
        base + "/api/balance/snapshots",
        json={"snapshot_date": date, "label": label},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
