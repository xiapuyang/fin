"""Built-in category definitions — single source of truth.

All four previous structures (EXPENSE_CATEGORIES, INCOME_CATEGORIES,
BUILTIN_CATEGORY_COLORS, BUILTIN_CATEGORY_IDS) are derived from
BUILTIN_CATEGORIES so there is no risk of inconsistency.

IDs 0001–0024 are permanent and never reused.
Custom categories continue from 0025 (see categories_store.py).
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
        "name": "保险",
        "bg": "#DDE7FA",
        "text": "#2964D9",
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
        "name": "汽车",
        "bg": "#D8DDE3",
        "text": "#2C3E50",
    },
    {
        "id": "0010",
        "direction": "expense",
        "name": "留学",
        "bg": "#E8DEF6",
        "text": "#7A4FC8",
    },
    {
        "id": "0011",
        "direction": "expense",
        "name": "课程培训",
        "bg": "#DEE9F2",
        "text": "#5C8FB8",
    },
    {
        "id": "0012",
        "direction": "expense",
        "name": "订阅",
        "bg": "#ECF1D2",
        "text": "#8DA82A",
    },
    {
        "id": "0013",
        "direction": "expense",
        "name": "旅游",
        "bg": "#D6EEDF",
        "text": "#1F8A4C",
    },
    {
        "id": "0014",
        "direction": "expense",
        "name": "子女教育",
        "bg": "#EBDDD0",
        "text": "#8E4A1B",
    },
    {
        "id": "0015",
        "direction": "expense",
        "name": "份子钱",
        "bg": "#F2D6E6",
        "text": "#B83887",
    },
    {
        "id": "0016",
        "direction": "expense",
        "name": "礼物",
        "bg": "#FBE3E1",
        "text": "#E0837C",
    },
    {
        "id": "0017",
        "direction": "expense",
        "name": "孝敬父母",
        "bg": "#F4ECD0",
        "text": "#B89638",
    },
    {
        "id": "0018",
        "direction": "expense",
        "name": "红包",
        "bg": "#F5DAD7",
        "text": "#BA3737",
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
        "id": "0022",
        "direction": "income",
        "name": "退税",
        "bg": "#DDE7FA",
        "text": "#2964D9",
    },
    {
        "id": "0023",
        "direction": "income",
        "name": "期权",
        "bg": "#E8DEF6",
        "text": "#7A4FC8",
    },
    {
        "id": "0024",
        "direction": "income",
        "name": "其他",
        "bg": "#ECEDEF",
        "text": "#6B7280",
    },
]

BUILTIN_MAX_ID = int(BUILTIN_CATEGORIES[-1]["id"])

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

# direction → {name → id} (used by migration backfill and CSV import)
BUILTIN_CATEGORY_IDS: dict[str, dict[str, str]] = {
    "expense": {
        c["name"]: c["id"] for c in BUILTIN_CATEGORIES if c["direction"] == "expense"
    },
    "income": {
        c["name"]: c["id"] for c in BUILTIN_CATEGORIES if c["direction"] == "income"
    },
}

# ── CSV import maps ───────────────────────────────────────────────────────────

# Notion import label → category ID
SUBCATEGORY_MAP: dict[str, str] = {
    "聚餐请客": "0001",  # dining
    "回家机票高铁": "0002",  # transportation
    "加油": "0009",  # car
    "停车费": "0009",  # car
    "保险": "0003",  # insurance
    "汽车保险": "0009",  # car
    "汽车维修保险": "0009",  # car
    "父母保险": "0003",  # insurance
    "保险, 留学/run/移民": "0003",  # insurance
    "买衣服": "0004",  # shopping
    "家居家电": "0004",  # shopping
    "电子产品": "0004",  # shopping
    "日常购物": "0004",  # shopping
    "老婆": "0016",  # gift
    "手机": "0004",  # shopping
    "份子钱": "0015",  # wedding gift
    "压岁钱": "0018",  # red envelope
    "孝敬父母": "0017",  # filial expenses
    "孝敬长辈": "0017",  # filial expenses
    "孝敬父母, 孝敬长辈": "0017",  # filial expenses
    "孝敬父母, 送礼": "0017",  # filial expenses
    "送礼": "0016",  # gift
    "医疗": "0005",  # healthcare
    "父母医疗": "0005",  # healthcare
    "体检": "0005",  # healthcare
    "子女医保": "0005",  # healthcare
    "社保": "0006",  # social insurance
    "党费": "0006",  # social insurance
    "租房": "0007",  # rent
    "房屋维修": "0007",  # rent
    "房产购买": "0007",  # rent
    "留学/run/移民, 租房": "0007",  # rent
    "汽车": "0009",  # car
    "汽车保养": "0009",  # car
    "汽车维修自费": "0009",  # car
    "留学/run/移民": "0010",  # study abroad
    "会员VIP": "0012",  # subscription
    "chatGPT": "0012",  # subscription
    "chatGPT, 会员VIP": "0012",  # subscription
    "AI": "0012",  # subscription
    "手机套餐": "0012",  # subscription
    "课程学习": "0012",  # subscription
    "Poker": "0012",  # subscription
    "旅游": "0013",  # travel
    "娱乐": "0013",  # travel
    "演唱会表演": "0013",  # travel
    "吉他": "0013",  # travel
    "电影": "0013",  # travel
    "幼儿园": "0014",  # children's education
    "早教": "0014",  # children's education
    "托班": "0014",  # children's education
    "幼儿园, 早教": "0014",  # children's education
    "证件": "0019",  # other
    "公益": "0019",  # other
}

RECURRING_TYPE_MAP: dict[str, str | None] = {
    "每月定期": "monthly",
    "每年定期": "annual",
    "每半年定期": "semi_annual",
    "每四个月定期": "every_4months",
    "单次": None,
    "": None,
}

RECURRING_LABEL: dict[str, str] = {
    "monthly": "每月",
    "annual": "每年",
    "semi_annual": "每半年",
    "every_4months": "每四个月",
}
