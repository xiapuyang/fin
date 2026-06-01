"""POST a list of {name, parent_name?} to /api/balance/accounts/bulk.

Usage:
    python setup_accounts.py --rows rows.json
    python setup_accounts.py --rows '[{"name": "IB"}, ...]'
    FIN_API_URL=... python setup_accounts.py --rows rows.json
"""

import argparse
import json
import sys
from pathlib import Path

import requests

from _fin_url import resolve_base as _resolve_base
from _utils import _err


def post(rows: list[dict]) -> dict:
    """POST balance account rows to /api/balance/accounts/bulk.

    Args:
        rows: List of {name, parent_name?} dicts.

    Returns:
        BulkResponse-shaped dict with created, skipped, and errors keys.
    """
    base = _resolve_base()
    url = base + "/api/balance/accounts/bulk"
    try:
        r = requests.post(url, json=rows, timeout=30)
    except requests.exceptions.RequestException:
        return _err(
            f"could not reach fin at {base} — start with `uv run python serve.py`",
            prefix="fin-accounts",
        )
    if r.status_code >= 400:
        return _err(f"{r.status_code}: {r.text}", payload=rows, prefix="fin-accounts")
    try:
        return r.json()
    except ValueError:
        return {"errors": [{"reason": "non-json-response", "details": r.text[:500]}]}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", required=True)
    args = p.parse_args()
    raw = args.rows.lstrip()
    rows = (
        json.loads(raw)
        if raw.startswith(("[", "{"))
        else json.loads(Path(args.rows).read_text())
    )
    result = post(rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
