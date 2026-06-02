"""Ledger category store.

Built-in categories (IDs 0001–0024) are defined in ledger_categories.py and
are always active (status Y). Custom categories live in
data/ledger_categories.json with sequential IDs continuing from 0025.
Deleting a custom category sets status D (soft delete) so IDs are never reused.
"""

import json
import logging
import os
import tempfile

from fin.config import LEDGER_CATEGORIES_PATH
from fin.ledger_categories import BUILTIN_ID_MAP, BUILTIN_MAX_ID

logger = logging.getLogger(__name__)


def _load_custom() -> list[dict]:
    if not LEDGER_CATEGORIES_PATH.exists():
        return []
    try:
        data = json.loads(LEDGER_CATEGORIES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        logger.error(
            "Failed to parse %s — returning empty list", LEDGER_CATEGORIES_PATH
        )
        return []
    except OSError:
        return []


def _save_custom(rows: list[dict]) -> None:
    text = json.dumps(rows, indent=2, ensure_ascii=False)
    parent = LEDGER_CATEGORIES_PATH.parent
    with tempfile.NamedTemporaryFile(
        "w", dir=parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as f:
        f.write(text)
        tmp = f.name
    os.replace(tmp, LEDGER_CATEGORIES_PATH)


def _next_id() -> str:
    """Next custom ID, always above the reserved built-in ceiling.

    Existing customs in the reserved range (e.g. early installs that started
    customs at a lower floor) remain valid for lookup, but new IDs never
    collide with the reserved range.
    """
    rows = _load_custom()
    existing = [int(c["id"]) for c in rows if str(c.get("id", "")).isdigit()]
    next_num = max([*existing, BUILTIN_MAX_ID]) + 1
    return f"{next_num:04d}"


def _name_taken(direction: str, name: str, ignore_id: str | None = None) -> bool:
    """Return True if name is already used in direction (built-in or active custom)."""
    for cat in BUILTIN_ID_MAP.values():
        if cat["direction"] == direction and cat["name"] == name:
            return True
    return any(
        c.get("direction") == direction
        and c.get("name") == name
        and c.get("status", "Y") == "Y"
        and c.get("id") != ignore_id
        for c in _load_custom()
    )


def find(cat_id: str) -> dict | None:
    """Return category record by ID, or None if not found / soft-deleted."""
    if cat_id in BUILTIN_ID_MAP:
        return BUILTIN_ID_MAP[cat_id]
    for c in _load_custom():
        if c.get("id") == cat_id and c.get("status", "Y") != "D":
            return {**c, "is_builtin": False}
    return None


def list_all() -> list[dict]:
    """Return all active categories: built-ins first, then active customs."""
    builtins = list(BUILTIN_ID_MAP.values())
    customs = [
        {**c, "is_builtin": False}
        for c in _load_custom()
        if c.get("status", "Y") == "Y"
    ]
    return builtins + customs


def add(direction: str, name: str, bg_color: str, text_color: str) -> dict:
    """Append a new custom category with the next sequential ID."""
    if direction not in ("expense", "income"):
        raise ValueError(f"invalid direction: {direction!r}")
    if _name_taken(direction, name):
        raise ValueError(f"category {name!r} already exists for {direction}")
    rows = _load_custom()
    new_id = _next_id()
    rows.append(
        {
            "id": new_id,
            "direction": direction,
            "name": name,
            "bg_color": bg_color,
            "text_color": text_color,
            "status": "Y",
        }
    )
    _save_custom(rows)
    return {
        "id": new_id,
        "direction": direction,
        "name": name,
        "bg_color": bg_color,
        "text_color": text_color,
        "is_builtin": False,
        "status": "Y",
        "sort_order": BUILTIN_MAX_ID + len(rows),
    }


def update(
    cat_id: str,
    name: str | None = None,
    bg_color: str | None = None,
    text_color: str | None = None,
) -> dict:
    """Update a custom category. Built-ins raise PermissionError."""
    if cat_id in BUILTIN_ID_MAP:
        raise PermissionError("built-in categories are read-only")
    rows = _load_custom()
    for row in rows:
        if row.get("id") != cat_id:
            continue
        if row.get("status") == "D":
            raise KeyError(cat_id)
        if name is not None and name != row["name"]:
            if _name_taken(row["direction"], name, ignore_id=cat_id):
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
    raise KeyError(cat_id)


def delete(cat_id: str) -> None:
    """Soft-delete a custom category (sets status D). Built-ins raise PermissionError."""
    if cat_id in BUILTIN_ID_MAP:
        raise PermissionError("built-in categories cannot be deleted")
    rows = _load_custom()
    for row in rows:
        if row.get("id") == cat_id:
            if row.get("status") == "D":
                raise KeyError(cat_id)
            row["status"] = "D"
            _save_custom(rows)
            return
    raise KeyError(cat_id)
