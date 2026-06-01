"""Parse user input into list[dict] rows. Supports csv (text or file) and txt.

txt is one-value-per-line input — only useful for single-required-field domains
(watchlist). Each line becomes `{<key>: line}`. Default key is `symbol` to
match the watchlist canonical schema; pass --txt-key to override (e.g. for a
future single-field domain).

Library usage:
    from parse_input import parse
    rows = parse(path='in.csv', format='csv')
    rows = parse(path='symbols.txt', format='txt', txt_key='symbol')

CLI usage (matches SKILL.md contract):
    python parse_input.py <path|->  --format csv|txt  [--txt-key KEY]
        '-' reads stdin; output is JSON list to stdout.
"""

import argparse
import csv
import io
import json
import sys
from typing import Any


def parse(
    text: str | None = None,
    path: str | None = None,
    format: str = "csv",
    txt_key: str = "symbol",
) -> list[dict[str, Any]]:
    if format == "txt":
        return _parse_txt(text or _read(path), key=txt_key)
    return _parse_csv(text or _read(path))


def _read(path: str | None) -> str:
    if not path:
        raise ValueError("text or path required")
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        cleaned = {
            (k.strip() if k else ""): (v.strip() if isinstance(v, str) else v)
            for k, v in raw.items()
            if k is not None
        }
        if any(v for v in cleaned.values()):
            rows.append(cleaned)
    return rows


def _parse_txt(text: str, key: str = "symbol") -> list[dict[str, Any]]:
    return [{key: line.strip()} for line in text.splitlines() if line.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("path", help="file path, or '-' for stdin")
    p.add_argument("--format", choices=("csv", "txt"), default="csv")
    p.add_argument(
        "--txt-key",
        default="symbol",
        help="key name for each line when --format=txt (default: symbol, matches watchlist)",
    )
    args = p.parse_args()
    text = sys.stdin.read() if args.path == "-" else None
    rows = parse(
        text=text,
        path=None if text is not None else args.path,
        format=args.format,
        txt_key=args.txt_key,
    )
    json.dump(rows, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
