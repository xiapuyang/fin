"""Persistent ledger categories.

Built-in categories are sourced from `fin.ledger_categories.BUILTIN_CATEGORY_COLORS`
and are immutable from the UI — they are never written to the JSON file.
User-added (custom) categories live in `data/ledger_categories.json`.

The merged view returned by `list_all()` interleaves both, marking each row
with an `is_builtin` flag so callers can enforce edit/delete permissions.
"""

import json
import uuid

from fin.config import LEDGER_CATEGORIES_PATH
from fin.ledger_categories import (
    BUILTIN_CATEGORY_COLORS,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
)

_FALLBACK_COLOR = {"bg": "#ECEDEF", "text": "#6B7280"}
_BUILTIN_NAMES = {
    "expense": set(EXPENSE_CATEGORIES),
    "income": set(INCOME_CATEGORIES),
}


def _load_custom() -> list[dict]:
    """Read the custom-category JSON file. Returns [] if missing or corrupt."""
    if not LEDGER_CATEGORIES_PATH.exists():
        return []
    try:
        data = json.loads(LEDGER_CATEGORIES_PATH.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_custom(rows: list[dict]) -> None:
    """Atomically persist custom categories to disk."""
    LEDGER_CATEGORIES_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False))


def _builtins() -> list[dict]:
    """Synthesize built-in category rows from in-code defaults."""
    out: list[dict] = []
    for direction, names in (
        ("expense", EXPENSE_CATEGORIES),
        ("income", INCOME_CATEGORIES),
    ):
        for i, name in enumerate(names):
            colors = BUILTIN_CATEGORY_COLORS.get(name, _FALLBACK_COLOR)
            out.append(
                {
                    "id": f"builtin:{direction}:{name}",
                    "direction": direction,
                    "name": name,
                    "bg_color": colors["bg"],
                    "text_color": colors["text"],
                    "is_builtin": True,
                    "sort_order": i,
                }
            )
    return out


def list_all() -> list[dict]:
    """Return built-ins followed by custom categories, all annotated with is_builtin."""
    base_count = {
        "expense": len(EXPENSE_CATEGORIES),
        "income": len(INCOME_CATEGORIES),
    }
    seen_keys: dict[str, int] = {}  # key = direction:name
    customs: list[dict] = []
    for i, raw in enumerate(_load_custom()):
        if not isinstance(raw, dict):
            continue
        direction = raw.get("direction")
        name = raw.get("name")
        if direction not in ("expense", "income") or not isinstance(name, str):
            continue
        key = f"{direction}:{name}"
        if key in seen_keys:
            continue  # silently dedupe corrupt JSON
        seen_keys[key] = i
        customs.append(
            {
                "id": raw.get("id") or str(uuid.uuid4()),
                "direction": direction,
                "name": name,
                "bg_color": raw.get("bg_color", _FALLBACK_COLOR["bg"]),
                "text_color": raw.get("text_color", _FALLBACK_COLOR["text"]),
                "is_builtin": False,
                "sort_order": base_count.get(direction, 0) + i,
            }
        )
    return _builtins() + customs


def find(id: str) -> dict | None:
    """Look up a custom category by id. Returns None for built-ins or unknown ids."""
    if id.startswith("builtin:"):
        return None
    for c in _load_custom():
        if c.get("id") == id:
            return dict(c)
    return None


def _name_taken(direction: str, name: str, ignore_id: str | None = None) -> bool:
    """Check both built-in and custom rows for a name collision in the given direction."""
    if name in _BUILTIN_NAMES.get(direction, set()):
        return True
    return any(
        c.get("direction") == direction
        and c.get("name") == name
        and c.get("id") != ignore_id
        for c in _load_custom()
    )


def add(direction: str, name: str, bg_color: str, text_color: str) -> dict:
    """Append a new custom category. Raises ValueError on duplicate name."""
    if _name_taken(direction, name):
        raise ValueError(f"category {name!r} already exists for {direction}")
    rows = _load_custom()
    new_id = str(uuid.uuid4())
    rows.append(
        {
            "id": new_id,
            "direction": direction,
            "name": name,
            "bg_color": bg_color,
            "text_color": text_color,
        }
    )
    _save_custom(rows)
    base_count = len(_BUILTIN_NAMES.get(direction, set()))
    return {
        "id": new_id,
        "direction": direction,
        "name": name,
        "bg_color": bg_color,
        "text_color": text_color,
        "is_builtin": False,
        "sort_order": base_count + len(rows) - 1,
    }


def update(
    id: str,
    name: str | None = None,
    bg_color: str | None = None,
    text_color: str | None = None,
) -> dict:
    """Update an existing custom category. Built-ins raise PermissionError."""
    if id.startswith("builtin:"):
        raise PermissionError("built-in categories are read-only")
    rows = _load_custom()
    for row in rows:
        if row.get("id") != id:
            continue
        if name is not None and name != row["name"]:
            if _name_taken(row["direction"], name, ignore_id=id):
                raise ValueError(
                    f"category {name!r} already exists for {row['direction']}"
                )
            row["name"] = name
        if bg_color is not None:
            row["bg_color"] = bg_color
        if text_color is not None:
            row["text_color"] = text_color
        _save_custom(rows)
        return {**row, "is_builtin": False, "sort_order": 0}
    raise KeyError(id)


def delete(id: str) -> None:
    """Remove a custom category. Built-ins raise PermissionError."""
    if id.startswith("builtin:"):
        raise PermissionError("built-in categories cannot be deleted")
    rows = _load_custom()
    remaining = [c for c in rows if c.get("id") != id]
    if len(remaining) == len(rows):
        raise KeyError(id)
    _save_custom(remaining)
