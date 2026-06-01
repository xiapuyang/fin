"""Preview an import: fetch existing rows, client-side dedup, print summary.

Usage:
    python preview.py --type alerts --rows rows.json
    python preview.py --type alerts --rows '[{"symbol":"AAPL",...}]'

--rows accepts either a path to a JSON file or an inline JSON list — autodetected
by leading '[' or '{'.

Dedup key fields are tuples of (incoming_alias, existing_alias). The fin backend
intentionally uses different names on POST (`AlertCreate.symbol`) vs GET
(`AlertResponse.code`); both sides are looked up via `.get(alias)` and the first
hit wins. When both schemas already use the same name (watchlist `symbol`), pass
a single-string entry.

URL resolution lives in _fin_url.resolve_base (FIN_API_URL > ~/.fin-dev marker
> port-conflict refusal > default :8888). Network failures degrade gracefully —
preview still shows local row count + sample, but flags that server-side dedup
numbers couldn't be computed.
"""

import argparse
import json
import sys

import requests

from _fin_url import resolve_base
from _utils import _load_rows

# Per-field tuple: (incoming_alias, existing_alias). String entry = same name
# on both sides. Add a new entry when fin's POST vs GET schemas diverge.
NATURAL_KEYS: dict[str, tuple[tuple[str, ...] | str, ...]] = {
    "alerts": (("symbol", "code"), ("condition", "cond"), ("value", "threshold")),
    "transactions": ("date", "code", "side", "shares", "price", "currency"),
    "holdings": ("account", "code", "snapshot_name"),
    "income": ("date", "source", "amount", "currency"),
    "ledger": ("direction", "name", "date", "amount"),
    "balance": ("snapshot_id", "side", "account_id", "sub_account_id", "category"),
    "watchlist": ("symbol",),
}

ENDPOINTS = {
    "alerts": "/api/alerts",
    "transactions": "/api/transactions",
    "holdings": "/api/holdings",
    "income": "/api/income",
    "ledger": "/api/ledger?page_size=200",
    "balance": "/api/balance/items",
    "watchlist": "/api/watchlist",
}


def _extract_key(row: dict, spec: tuple, side: int) -> tuple:
    """Build the dedup tuple. side=0 for incoming aliases, side=1 for existing."""
    out = []
    for field in spec:
        if isinstance(field, str):
            out.append(row.get(field))
        else:
            out.append(row.get(field[side]))
    return tuple(out)


def dedup(
    domain: str, incoming: list[dict], existing: list[dict]
) -> tuple[list[dict], int]:
    """Client-side dedup: filter incoming rows that already exist server-side.

    Args:
        domain: Import domain key (must be in NATURAL_KEYS).
        incoming: Canonical rows about to be posted.
        existing: Rows fetched from the server via GET /api/<domain>.

    Returns:
        Tuple of (new_rows, skipped_count) where new_rows excludes dupes.
    """
    spec = NATURAL_KEYS[domain]
    existing_keys = {_extract_key(e, spec, side=1) for e in existing}
    new: list[dict] = []
    skipped = 0
    for row in incoming:
        k = _extract_key(row, spec, side=0)
        if k in existing_keys:
            skipped += 1
        else:
            existing_keys.add(k)
            new.append(row)
    return new, skipped


def _fetch_existing(domain: str) -> list[dict] | None:
    """Fetch existing rows from the server for dedup comparison.

    Args:
        domain: Import domain key matching an entry in ENDPOINTS.

    Returns:
        List of existing row dicts, or None if the server is unreachable.
    """
    base = resolve_base()
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

    rows = _load_rows(args.rows)
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
