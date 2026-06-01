"""Resolve a single account name for transactions / holdings imports.

Workflow (called from SKILL.md runtime):
    1. fetch existing via GET /api/accounts
    2. if name matches an existing account -> return its dict
    3. otherwise return None and let the caller AskUserQuestion for
       currency / balance_account_id / cutoff_date, then POST.

Pure helpers — AskUserQuestion + POST happen in the orchestrating skill code.
"""

import requests

from _fin_url import resolve_base


def fetch_existing() -> list[dict]:
    base = resolve_base()
    r = requests.get(base + "/api/accounts", timeout=10)
    r.raise_for_status()
    body = r.json()
    return body if isinstance(body, list) else body.get("items", [])


def find(name: str, accounts: list[dict]) -> dict | None:
    for a in accounts:
        if a.get("name") == name:
            return a
    return None


def create(
    name: str,
    currency: str,
    balance_account_id: int | None = None,
    balance_sub_account_id: int | None = None,
    cutoff_date: str | None = None,
    note: str | None = None,
) -> dict:
    base = resolve_base()
    payload: dict = {"name": name, "currency": currency}
    if balance_account_id:
        payload["balance_account_id"] = balance_account_id
    if balance_sub_account_id:
        payload["balance_sub_account_id"] = balance_sub_account_id
    if cutoff_date:
        payload["cutoff_date"] = cutoff_date
    if note:
        payload["note"] = note
    r = requests.post(base + "/api/accounts", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()
