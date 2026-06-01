"""POST a canonical row list to the right /bulk endpoint.

Usage:
    python post_bulk.py --type alerts --rows rows.json
    python post_bulk.py --type alerts --rows '[{"symbol":"AAPL",...}]'
    FIN_API_URL=http://other:8000 python post_bulk.py --type ...

--rows accepts either a path to a JSON file or an inline JSON list — autodetected
by leading '[' or '{'.

Returns the server's BulkResponse JSON to stdout. Non-zero exit on error.
"""

import argparse
import json
import sys

import requests

from _fin_url import resolve_base
from _utils import _err, _load_rows

ENDPOINTS = {
    "alerts": "/api/alerts/bulk",
    "transactions": "/api/transactions/bulk",
    "holdings": "/api/holdings/bulk",
    "income": "/api/income/bulk",
    "ledger": "/api/ledger/bulk",
    "balance": "/api/balance/items/bulk",
    "watchlist": "/api/watchlist/bulk",
    "balance_accounts": "/api/balance/accounts/bulk",
}


def post(domain: str, rows: list[dict]) -> dict:
    """POST canonical rows to the fin bulk endpoint for the given domain.

    Args:
        domain: One of the keys in ENDPOINTS (alerts, transactions, etc.).
        rows: List of canonical row dicts matching the domain's schema.

    Returns:
        BulkResponse-shaped dict with created, skipped, and errors keys.
    """
    base = resolve_base()
    url = base + ENDPOINTS[domain]
    try:
        r = requests.post(url, json=rows, timeout=30)
    except requests.exceptions.RequestException:
        return _err(
            f"could not reach fin at {base} — start with `uv run python serve.py`"
        )
    if r.status_code >= 400:
        return _err(f"{r.status_code}: {r.text}", payload=rows)
    try:
        return r.json()
    except ValueError:
        return {"errors": [{"reason": "non-json-response", "details": r.text[:500]}]}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--type", required=True, choices=list(ENDPOINTS))
    p.add_argument("--rows", required=True)
    args = p.parse_args()
    rows = _load_rows(args.rows)
    result = post(args.type, rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
