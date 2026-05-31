"""POST a canonical row list to the right /bulk endpoint.

Usage:
    python post_bulk.py --type alerts --rows rows.json
    FIN_API_URL=http://other:8000 python post_bulk.py --type ...

Returns the server's BulkResponse JSON to stdout. Non-zero exit on error.
"""

import argparse
import json
import os
import socket
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

PROD_PORT = 8899
DEV_PORT = 18899


def _port_open(port: int) -> bool:
    """True if something is listening on 127.0.0.1:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _resolve_base() -> str:
    """Refuse if both prod (8899) and dev (18899) fin servers are live — we
    can't tell which one the user means. Otherwise honor FIN_API_URL or fall
    back to localhost:8899."""
    if _port_open(PROD_PORT) and _port_open(DEV_PORT):
        raise SystemExit(
            f"REFUSED: both prod ({PROD_PORT}) and dev ({DEV_PORT}) fin servers "
            "are running. Stop one and retry — the skill can't tell which one "
            "you mean."
        )
    return os.environ.get("FIN_API_URL", f"http://localhost:{PROD_PORT}")


def post(domain: str, rows: list[dict]) -> dict:
    base = _resolve_base()
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
