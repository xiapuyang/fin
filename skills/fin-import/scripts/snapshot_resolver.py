"""Resolve a balance snapshot by date for balance imports.

Pure helpers — AskUserQuestion + decision-to-create live in SKILL.md flow.

CLI usage (matches SKILL.md contract):
    python snapshot_resolver.py find --date YYYY-MM-DD
        prints the matching snapshot dict to stdout, or 'null' if none.
    python snapshot_resolver.py create --date YYYY-MM-DD --label TEXT
        POSTs a new snapshot and prints the created record.
"""

import argparse
import json
import sys

import requests

from _fin_url import resolve_base


def _fetch_all() -> list[dict]:
    base = resolve_base()
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
    base = resolve_base()
    r = requests.post(
        base + "/api/balance/snapshots",
        json={"snapshot_date": date, "label": label},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="find snapshot by date; prints null if none")
    f.add_argument("--date", required=True, help="YYYY-MM-DD")
    c = sub.add_parser("create", help="create a new snapshot")
    c.add_argument("--date", required=True, help="YYYY-MM-DD")
    c.add_argument("--label", required=True)
    args = p.parse_args()
    result = (
        find_by_date(args.date) if args.cmd == "find" else create(args.date, args.label)
    )
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
