"""Parse user input into list[dict] rows. Supports csv (text or file) and txt."""

import csv
import io
from typing import Any


def parse(
    text: str | None = None, path: str | None = None, format: str = "csv"
) -> list[dict[str, Any]]:
    if format == "txt":
        return _parse_txt(text or _read(path))
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


def _parse_txt(text: str) -> list[dict[str, Any]]:
    return [{"value": line.strip()} for line in text.splitlines() if line.strip()]
