"""POST a canonical row list to the right /bulk endpoint.

Usage:
    python post_bulk.py --type alerts --rows rows.json
    FIN_API_URL=http://other:8000 python post_bulk.py --type ...

Returns the server's BulkResponse JSON to stdout. Non-zero exit on error.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

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
    base = os.environ.get("FIN_API_URL", "http://localhost:8899")
    url = base + ENDPOINTS[domain]
    try:
        r = requests.post(url, json=rows, timeout=30)
    except requests.ConnectionError:
        return _err(
            f"could not reach fin at {base} — start with `uv run python serve.py`"
        )
    if r.status_code >= 400:
        return _err(f"{r.status_code}: {r.text}", payload=rows)
    return r.json()


def _err(reason: str, payload=None) -> dict:
    ts = int(time.time())
    err_path = Path(f"/tmp/fin-import-error-{ts}.json")
    err_path.write_text(
        json.dumps(
            {"reason": reason, "payload": payload},
            indent=2,
            ensure_ascii=False,
        )
    )
    return {
        "created": 0,
        "skipped": 0,
        "errors": [{"reason": reason, "details": str(err_path)}],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--type", required=True, choices=list(ENDPOINTS))
    p.add_argument("--rows", required=True)
    args = p.parse_args()
    rows = json.loads(Path(args.rows).read_text())
    result = post(args.type, rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
