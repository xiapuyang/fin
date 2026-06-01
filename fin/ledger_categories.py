"""Built-in category definitions — single source of truth.

All derived structures (BUILTIN_ID_MAP, BUILTIN_CATEGORY_IDS) are computed
from BUILTIN_CATEGORIES so there is no risk of inconsistency.

ID ranges:
    0001–0100   built-in expense  (current use: 0001–0011)
    0101–0200   built-in income   (current use: 0101–0103)
    0201+       customs           (see categories_store.py)

Only a universal core is shipped in source; culture- or lifestyle-specific
categories live in data/ledger_categories.json on each install so the
source tree stays neutral.
"""

# ── Single config ─────────────────────────────────────────────────────────────

BUILTIN_CATEGORIES: list[dict] = [
    # ── Expense ──────────────────────────────────────────────────────────────
    {
        "id": "0001",
        "direction": "expense",
        "name": "餐饮",
        "bg": "#FBE3D6",
        "text": "#E85D2C",
    },
    {
        "id": "0002",
        "direction": "expense",
        "name": "交通",
        "bg": "#D6F0F2",
        "text": "#14959E",
    },
    {
        "id": "0003",
        "direction": "expense",
        "name": "购物",
        "bg": "#FAD9E7",
        "text": "#D9347A",
    },
    {
        "id": "0004",
        "direction": "expense",
        "name": "医疗",
        "bg": "#FBDADA",
        "text": "#D62828",
    },
    {
        "id": "0005",
        "direction": "expense",
        "name": "保险",
        "bg": "#DDE7FA",
        "text": "#2964D9",
    },
    {
        "id": "0006",
        "direction": "expense",
        "name": "社保",
        "bg": "#DEE1EE",
        "text": "#4F5B8C",
    },
    {
        "id": "0007",
        "direction": "expense",
        "name": "房租",
        "bg": "#FAEDD2",
        "text": "#C8821F",
    },
    {
        "id": "0008",
        "direction": "expense",
        "name": "房贷",
        "bg": "#E5DACE",
        "text": "#5C3A21",
    },
    {
        "id": "0009",
        "direction": "expense",
        "name": "订阅",
        "bg": "#ECF1D2",
        "text": "#8DA82A",
    },
    {
        "id": "0010",
        "direction": "expense",
        "name": "旅游",
        "bg": "#D6EEDF",
        "text": "#1F8A4C",
    },
    {
        "id": "0011",
        "direction": "expense",
        "name": "其他",
        "bg": "#ECEDEF",
        "text": "#6B7280",
    },
    # ── Income ───────────────────────────────────────────────────────────────
    {
        "id": "0101",
        "direction": "income",
        "name": "工资",
        "bg": "#D6EEDF",
        "text": "#1F8A4C",
    },
    {
        "id": "0102",
        "direction": "income",
        "name": "奖金",
        "bg": "#FAEDD2",
        "text": "#C8821F",
    },
    {
        "id": "0103",
        "direction": "income",
        "name": "其他",
        "bg": "#ECEDEF",
        "text": "#6B7280",
    },
]

# Reserved ceiling: expense lives in 0001-0100, income in 0101-0200.
# Custom IDs always start from 0201 even if many reserved slots aren't yet used.
BUILTIN_EXPENSE_MAX_ID = 100
BUILTIN_INCOME_MAX_ID = 200
BUILTIN_MAX_ID = BUILTIN_INCOME_MAX_ID  # ceiling for categories_store._next_id

# Fail fast on typos: duplicate IDs would silently collapse into BUILTIN_ID_MAP,
# and out-of-range IDs would shadow custom categories on user installs.
_ids = [c["id"] for c in BUILTIN_CATEGORIES]
assert len(_ids) == len(set(_ids)), f"duplicate built-in IDs: {_ids}"
for _c in BUILTIN_CATEGORIES:
    _n = int(_c["id"])
    if _c["direction"] == "expense":
        assert 1 <= _n <= BUILTIN_EXPENSE_MAX_ID, (
            f"expense ID {_c['id']} out of 0001-{BUILTIN_EXPENSE_MAX_ID:04d} range"
        )
    elif _c["direction"] == "income":
        assert BUILTIN_EXPENSE_MAX_ID < _n <= BUILTIN_INCOME_MAX_ID, (
            f"income ID {_c['id']} out of "
            f"{BUILTIN_EXPENSE_MAX_ID + 1:04d}-{BUILTIN_INCOME_MAX_ID:04d} range"
        )
    else:
        raise AssertionError(f"unknown direction in built-in: {_c}")

# ── Derived indexes ───────────────────────────────────────────────────────────

# id → full record (O(1) lookup used by categories_store and stats)
BUILTIN_ID_MAP: dict[str, dict] = {
    c["id"]: {
        "id": c["id"],
        "direction": c["direction"],
        "name": c["name"],
        "bg_color": c["bg"],
        "text_color": c["text"],
        "is_builtin": True,
        "status": "Y",
    }
    for c in BUILTIN_CATEGORIES
}

# direction → {name → id} (used by migration backfill)
BUILTIN_CATEGORY_IDS: dict[str, dict[str, str]] = {
    "expense": {
        c["name"]: c["id"] for c in BUILTIN_CATEGORIES if c["direction"] == "expense"
    },
    "income": {
        c["name"]: c["id"] for c in BUILTIN_CATEGORIES if c["direction"] == "income"
    },
}
