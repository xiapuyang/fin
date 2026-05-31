"""POST a list of {name, parent_name?} to /api/balance/accounts/bulk.

Usage:
    python setup_accounts.py --rows rows.json
    FIN_API_URL=... python setup_accounts.py --rows rows.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests


_PROD_TARGETS = ("localhost:8899", "127.0.0.1:8899")


def _resolve_base() -> str:
    """Refuse prod writes from a dev machine (~/.fin-dev marker present)."""
    base = os.environ.get("FIN_API_URL", "http://localhost:8899")
    if (Path.home() / ".fin-dev").exists() and any(t in base for t in _PROD_TARGETS):
        raise SystemExit(
            "REFUSED: ~/.fin-dev marker present (dev machine) but the target "
            f"is prod ({base}). Either:\n"
            "  export FIN_API_URL=http://127.0.0.1:18899  # point at dev server\n"
            "  rm ~/.fin-dev                              # really mean to write prod"
        )
    return base


def post(rows: list[dict]) -> dict:
    base = _resolve_base()
    url = base + "/api/balance/accounts/bulk"
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
    err_path = Path(f"/tmp/fin-accounts-error-{ts}.json")
    err_path.write_text(
        json.dumps({"reason": reason, "payload": payload}, indent=2, ensure_ascii=False)
    )
    return {
        "created": 0,
        "skipped": 0,
        "errors": [{"reason": reason, "details": str(err_path)}],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", required=True)
    args = p.parse_args()
    rows = json.loads(Path(args.rows).read_text())
    result = post(rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
