"""Parse account hierarchy from user input into [{name, parent_name?}, ...]."""

import csv
import io


def _split_pair(line: str) -> tuple[str, str | None]:
    for sep in ("/", " > ", " > ", ">"):
        if sep in line:
            parent, sub = line.split(sep, 1)
            return parent.strip(), sub.strip() or None
    return line.strip(), None


def parse_text(text: str) -> list[dict]:
    """One row per line. Separators: /, >, ' > '. # starts a comment line."""
    seen_parents: set[str] = set()
    rows: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parent, sub = _split_pair(line)
        if not parent:
            continue
        if parent not in seen_parents:
            rows.append({"name": parent})
            seen_parents.add(parent)
        if sub:
            rows.append({"name": sub, "parent_name": parent})
    return rows


def parse_csv(text: str) -> list[dict]:
    """CSV with columns 'parent' (required) and 'sub' (optional)."""
    reader = csv.DictReader(io.StringIO(text))
    seen_parents: set[str] = set()
    rows: list[dict] = []
    for raw in reader:
        parent = (raw.get("parent") or "").strip()
        sub = (raw.get("sub") or "").strip()
        if not parent:
            continue
        if parent not in seen_parents:
            rows.append({"name": parent})
            seen_parents.add(parent)
        if sub:
            rows.append({"name": sub, "parent_name": parent})
    return rows
