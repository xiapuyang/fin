"""Built-in category definitions — single source of truth.

All derived structures (BUILTIN_ID_MAP, BUILTIN_CATEGORY_IDS) are computed
from BUILTIN_CATEGORIES so there is no risk of inconsistency.

IDs 0001–0100 are reserved for built-ins (headroom for future additions).
Only a universal core is shipped in source; culture- or lifestyle-specific
categories live in data/ledger_categories.json on each install so the
source tree stays neutral. Custom user-added categories begin at 0101
(see categories_store.py).
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
        "id": "0004",
        "direction": "expense",
        "name": "购物",
        "bg": "#FAD9E7",
        "text": "#D9347A",
    },
    {
        "id": "0005",
        "direction": "expense",
        "name": "医疗",
        "bg": "#FBDADA",
        "text": "#D62828",
    },
    {
        "id": "0007",
        "direction": "expense",
        "name": "房租",
        "bg": "#FAEDD2",
        "text": "#C8821F",
    },
    {
        "id": "0012",
        "direction": "expense",
        "name": "订阅",
        "bg": "#ECF1D2",
        "text": "#8DA82A",
    },
    {
        "id": "0019",
        "direction": "expense",
        "name": "其他",
        "bg": "#ECEDEF",
        "text": "#6B7280",
    },
    # ── Income ───────────────────────────────────────────────────────────────
    {
        "id": "0020",
        "direction": "income",
        "name": "工资",
        "bg": "#D6EEDF",
        "text": "#1F8A4C",
    },
    {
        "id": "0021",
        "direction": "income",
        "name": "奖金",
        "bg": "#FAEDD2",
        "text": "#C8821F",
    },
    {
        "id": "0024",
        "direction": "income",
        "name": "其他",
        "bg": "#ECEDEF",
        "text": "#6B7280",
    },
]

# Reserved ceiling: IDs 0001–0100 are reserved for built-ins. Custom IDs
# always start from 0101 even if many reserved slots aren't yet used.
BUILTIN_MAX_ID = 100

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
