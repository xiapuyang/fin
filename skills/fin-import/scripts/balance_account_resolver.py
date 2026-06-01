"""Balance account lookup and creation against the current fin env.

Subcommands:
    list                — print all balance_accounts as JSON
                          (id, parent_id, name, parent_name)
    create --name NAME [--parent-id N]
                        — POST /api/balance/accounts; print created record.
                          Omit --parent-id to create a top-level (parent) account.

Why no matching logic here: semantic mapping of free-form account names
(e.g. "招商" → "招商银行", "IB" → "IBKR" or existing "IB") is decided by the
skill at runtime against the live tree and proposed to the user via
AskUserQuestion. This script stays a thin shim around the API so the
env-aware base URL (dev vs prod) is the single source of truth — never read
filesystem JSON under data/ or data-dev/.
"""

import argparse
import json
import sys

import requests

from _fin_url import resolve_base


def list_accounts() -> list[dict]:
    base = resolve_base()
    r = requests.get(base + "/api/balance/accounts", timeout=10)
    r.raise_for_status()
    rows = r.json()
    by_id = {a["id"]: a for a in rows}
    return [
        {
            "id": a["id"],
            "parent_id": a.get("parent_id"),
            "name": a["name"],
            "parent_name": by_id[a["parent_id"]]["name"]
            if a.get("parent_id") and a["parent_id"] in by_id
            else None,
        }
        for a in rows
    ]


def create_account(name: str, parent_id: int | None) -> dict:
    base = resolve_base()
    body: dict = {"name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id
    r = requests.post(base + "/api/balance/accounts", json=body, timeout=10)
    if r.status_code == 409:
        raise SystemExit(
            f"account {name!r} (parent_id={parent_id}) already exists — refetch with `list`"
        )
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    cp = sub.add_parser("create")
    cp.add_argument("--name", required=True)
    cp.add_argument("--parent-id", type=int, default=None)
    args = p.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_accounts(), ensure_ascii=False))
    elif args.cmd == "create":
        print(json.dumps(create_account(args.name, args.parent_id), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
