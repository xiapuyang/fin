"""Ledger category lookup and creation against the current fin env.

Subcommands:
    list                       — print all active categories as JSON (id, direction, name)
    create --direction D --name NAME [--bg #HEX] [--text #HEX]
                               — POST a new custom category; print created record

Why no matching logic here: semantic mapping (e.g. "饮食" → "餐饮", "Uber" →
"交通") is decided by the skill at runtime against the live category list and
proposed to the user via AskUserQuestion. This script intentionally stays a
thin shim around the API so the env-aware base URL (dev vs prod) is the only
source of truth — never read filesystem JSON under data/ or data-dev/.
"""

import argparse
import json
import sys

import requests

from _fin_url import resolve_base

# Neutral defaults for new custom categories — user can recolor in the UI.
DEFAULT_BG = "#E5E7EB"
DEFAULT_TEXT = "#374151"


def list_categories() -> list[dict]:
    base = resolve_base()
    r = requests.get(base + "/api/categories", timeout=10)
    r.raise_for_status()
    return [
        {"id": c["id"], "direction": c["direction"], "name": c["name"]}
        for c in r.json()
        if c.get("status", "Y") != "D"
    ]


def create_category(direction: str, name: str, bg: str, text: str) -> dict:
    if direction not in ("expense", "income"):
        raise SystemExit(f"direction must be expense|income, got {direction!r}")
    base = resolve_base()
    r = requests.post(
        base + "/api/categories",
        json={
            "direction": direction,
            "name": name,
            "bg_color": bg,
            "text_color": text,
        },
        timeout=10,
    )
    if r.status_code == 409:
        raise SystemExit(
            f"category {name!r} already exists for {direction} — refetch with `list`"
        )
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    cp = sub.add_parser("create")
    cp.add_argument("--direction", required=True, choices=("expense", "income"))
    cp.add_argument("--name", required=True)
    cp.add_argument("--bg", default=DEFAULT_BG)
    cp.add_argument("--text", default=DEFAULT_TEXT)
    args = p.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_categories(), ensure_ascii=False))
    elif args.cmd == "create":
        print(
            json.dumps(
                create_category(args.direction, args.name, args.bg, args.text),
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
