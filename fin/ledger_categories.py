EXPENSE_CATEGORIES = [
    "餐饮",
    "交通",
    "保险",
    "购物",
    "医疗",
    "社保",
    "房租",
    "房贷",
    "汽车",
    "留学",
    "课程培训",
    "订阅",
    "旅游",
    "子女教育",
    "份子钱",
    "礼物",
    "孝敬父母",
    "红包",
    "其他",
]

INCOME_CATEGORIES = ["工资", "奖金", "退税", "期权", "其他"]

# Source of truth for built-in category colors. The frontend reads from
# /api/categories which composes this map with custom rows from the JSON
# store. Keep ordering consistent with EXPENSE_CATEGORIES / INCOME_CATEGORIES
# so sort_order stays stable.
BUILTIN_CATEGORY_COLORS: dict[str, dict[str, str]] = {
    # Expense — 18 hues spread across the wheel for visual distinction
    "餐饮": {"bg": "#FBE3D6", "text": "#E85D2C"},  # orange
    "交通": {"bg": "#D6F0F2", "text": "#14959E"},  # teal
    "保险": {"bg": "#DDE7FA", "text": "#2964D9"},  # royal blue
    "购物": {"bg": "#FAD9E7", "text": "#D9347A"},  # pink
    "医疗": {"bg": "#FBDADA", "text": "#D62828"},  # red
    "社保": {"bg": "#DEE1EE", "text": "#4F5B8C"},  # slate
    "房租": {"bg": "#FAEDD2", "text": "#C8821F"},  # gold
    "房贷": {"bg": "#E5DACE", "text": "#5C3A21"},  # dark brown
    "汽车": {"bg": "#D8DDE3", "text": "#2C3E50"},  # charcoal
    "留学": {"bg": "#E8DEF6", "text": "#7A4FC8"},  # violet
    "课程培训": {"bg": "#DEE9F2", "text": "#5C8FB8"},  # steel blue
    "订阅": {"bg": "#ECF1D2", "text": "#8DA82A"},  # olive
    "旅游": {"bg": "#D6EEDF", "text": "#1F8A4C"},  # emerald
    "子女教育": {"bg": "#EBDDD0", "text": "#8E4A1B"},  # sienna
    "份子钱": {"bg": "#F2D6E6", "text": "#B83887"},  # magenta
    "礼物": {"bg": "#FBE3E1", "text": "#E0837C"},  # warm rose
    "孝敬父母": {"bg": "#F4ECD0", "text": "#B89638"},  # muted amber
    "红包": {"bg": "#F5DAD7", "text": "#BA3737"},  # brick red
    "其他": {"bg": "#ECEDEF", "text": "#6B7280"},  # grey
    # Income
    "工资": {"bg": "#D6EEDF", "text": "#1F8A4C"},
    "奖金": {"bg": "#FAEDD2", "text": "#C8821F"},
    "退税": {"bg": "#DDE7FA", "text": "#2964D9"},
    "期权": {"bg": "#E8DEF6", "text": "#7A4FC8"},
}

SUBCATEGORY_MAP: dict[str, str] = {
    "聚餐请客": "餐饮",
    "回家机票高铁": "交通",
    "加油": "交通",
    "停车费": "交通",
    "保险": "保险",
    "汽车保险": "保险",
    "汽车维修保险": "保险",
    "父母保险": "保险",
    "保险, 留学/run/移民": "保险",
    "买衣服": "购物",
    "家居家电": "购物",
    "电子产品": "购物",
    "日常购物": "购物",
    "老婆": "购物",
    "手机": "购物",
    "份子钱": "购物",
    "压岁钱": "购物",
    "孝敬父母": "购物",
    "孝敬长辈": "购物",
    "孝敬父母, 孝敬长辈": "购物",
    "孝敬父母, 送礼": "购物",
    "送礼": "购物",
    "医疗": "医疗",
    "父母医疗": "医疗",
    "体检": "医疗",
    "子女医保": "医疗",
    "社保": "社保",
    "党费": "社保",
    "租房": "房租",
    "房屋维修": "房租",
    "房产购买": "房租",
    "留学/run/移民, 租房": "房租",
    "汽车": "汽车",
    "汽车保养": "汽车",
    "汽车维修自费": "汽车",
    "留学/run/移民": "留学",
    "会员VIP": "订阅",
    "chatGPT": "订阅",
    "chatGPT, 会员VIP": "订阅",
    "AI": "订阅",
    "手机套餐": "订阅",
    "课程学习": "订阅",
    "Poker": "订阅",
    "旅游": "旅游",
    "娱乐": "旅游",
    "演唱会表演": "旅游",
    "吉他": "旅游",
    "电影": "旅游",
    "幼儿园": "子女教育",
    "早教": "子女教育",
    "托班": "子女教育",
    "幼儿园, 早教": "子女教育",
    "证件": "其他",
    "公益": "其他",
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
