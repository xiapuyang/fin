"""Preview an import: fetch existing rows, client-side dedup, print summary.

Usage:
    python preview.py --type alerts --rows rows.json

Reads FIN_API_URL (default http://localhost:8899). Network failures degrade
gracefully — preview still shows local row count + sample, but flags that
server-side dedup numbers couldn't be computed.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

# Same keys server uses for pre-filter dedup.
NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "alerts": ("symbol", "condition", "value"),
    "transactions": ("date", "code", "side", "shares", "price", "currency"),
    "holdings": ("account", "code", "snapshot_name"),
    "income": ("date", "source", "amount", "currency"),
    "ledger": ("direction", "name", "date", "amount"),
    "balance": ("snapshot_id", "name", "side", "category"),
    "watchlist": ("symbol",),
}

ENDPOINTS = {
    "alerts": "/api/alerts",
    "transactions": "/api/transactions",
    "holdings": "/api/holdings",
    "income": "/api/income",
    "ledger": "/api/ledger",
    "balance": "/api/balance/items",
    "watchlist": "/api/watchlist",
}


def dedup(
    domain: str, incoming: list[dict], existing: list[dict]
) -> tuple[list[dict], int]:
    keys = NATURAL_KEYS[domain]
    existing_keys = {tuple(e.get(k) for k in keys) for e in existing}
    new: list[dict] = []
    skipped = 0
    for row in incoming:
        k = tuple(row.get(k) for k in keys)
        if k in existing_keys:
            skipped += 1
        else:
            existing_keys.add(k)
            new.append(row)
    return new, skipped


def _fetch_existing(domain: str) -> list[dict] | None:
    base = os.environ.get("FIN_API_URL", "http://localhost:8899")
    try:
        r = requests.get(base + ENDPOINTS[domain], timeout=10)
        r.raise_for_status()
        body = r.json()
        return body if isinstance(body, list) else body.get("items", [])
    except requests.RequestException:
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--type", required=True, choices=list(NATURAL_KEYS))
    p.add_argument("--rows", required=True)
    args = p.parse_args()

    rows = json.loads(Path(args.rows).read_text())
    existing = _fetch_existing(args.type)

    print(f"\n── fin import preview: {args.type} ──")
    if existing is None:
        print("⚠ could not reach fin — dedup skipped, showing local rows only")
        print(f"Will attempt: {len(rows)} rows")
        new = rows
    else:
        new, skipped = dedup(args.type, rows, existing)
        print(f"Will create: {len(new)}")
        print(f"Already exists (skip): {skipped}")

    print("Sample (first 3 new rows):")
    for i, r in enumerate(new[:3]):
        print(f"  [{i}] {json.dumps(r, ensure_ascii=False)}")
    if len(new) > 3:
        print(f"  ... and {len(new) - 3} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
