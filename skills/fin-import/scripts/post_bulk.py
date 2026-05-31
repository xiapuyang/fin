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


_PROD_TARGETS = ("localhost:8899", "127.0.0.1:8899")


def _is_dev_machine() -> bool:
    """Detect a dev machine via two independent markers.

    Either marker is sufficient — defense in depth so accidentally removing one
    doesn't disable protection.

    Source 1: ~/.fin-dev (user-home, global across repos).
    Source 2: <repo>/.dev-machine — walks up from this script's resolved real
    path (follows symlinks back to the source repo, so installations done via
    `ln -s` still benefit).
    """
    if (Path.home() / ".fin-dev").exists():
        return True
    real = Path(__file__).resolve()
    for parent in real.parents:
        if (parent / ".dev-machine").exists():
            return True
        if parent == parent.parent:  # filesystem root
            break
    return False


def _resolve_base() -> str:
    """Resolve the fin server URL and refuse prod writes from a dev machine.

    Normal users (no dev markers) get the existing behavior. Dev machines must
    target a non-prod URL OR set FIN_ALLOW_PROD=1 for the invocation. Removing
    the markers does NOT silently re-enable prod writes — only the explicit
    env var does.
    """
    base = os.environ.get("FIN_API_URL", "http://localhost:8899")
    if not _is_dev_machine():
        return base
    if not any(t in base for t in _PROD_TARGETS):
        return base
    if os.environ.get("FIN_ALLOW_PROD") == "1":
        return base
    raise SystemExit(
        "REFUSED: dev machine detected (~/.fin-dev or <repo>/.dev-machine) and "
        f"target is prod ({base}). To write prod once:\n"
        "  FIN_ALLOW_PROD=1 python scripts/post_bulk.py ...\n"
        "Or point at dev:\n"
        "  export FIN_API_URL=http://127.0.0.1:18899"
    )


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
