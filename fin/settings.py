"""Persistent app settings stored in data/settings.json."""

import json
import locale
import logging
import os
import sys
import tempfile

from fin.config import SETTINGS_PATH

logger = logging.getLogger(__name__)


def _detect_os_locale() -> str:
    """Detect OS UI locale for the first-launch language default.

    Returns:
        "zh" if the system locale indicates Chinese (zh, zh_CN, zh_TW,
        zh-Hans, zh-Hant, etc.), otherwise "en".

    Lookup order:
        1. locale.getlocale() — set on Mac/Linux by the C locale; on
           Windows it reflects the active console locale.
        2. POSIX env vars LC_ALL / LC_MESSAGES / LANG — populated on Mac
           and Linux even when getlocale() is empty.
        3. Win32 GetUserDefaultUILanguage — covers fresh Windows installs
           that have no locale env vars set.
    """
    code = ""
    try:
        loc = locale.getlocale()[0]
        if loc:
            code = loc
    except Exception:
        pass

    if not code:
        for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
            v = os.environ.get(var, "").strip()
            if v and v.upper() not in ("C", "POSIX"):
                code = v
                break

    if not code and sys.platform == "win32":
        try:
            import ctypes

            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary = lcid & 0x3FF  # PRIMARYLANGID
            return "zh" if primary == 0x04 else "en"  # 0x04 = LANG_CHINESE
        except Exception:
            pass

    return "zh" if code.lower().startswith("zh") else "en"


_DEFAULTS = {
    "notify_email": "",
    "notify_enabled": True,
    "timezone": "",
    "display_name": "",
    "rebalance": None,
    "birth_date": "",
    "fire_monthly_exp": None,
    "fire_cagr": None,
    "fire_monthly": 8000,
    "fire_swr": 4.0,
    "fire_manual_age": 32,
    "fire_inflation": 3,
    "fire_target_age": 50,
    "fire_mc_sigma": 15,
    "fire_life_expectancy": 80,
    "currency": "CNY",
    "privacy_mask": False,
    "language": _detect_os_locale(),
    "enabled_markets": ["us"],
}


def load() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULTS)
    try:
        return {**_DEFAULTS, **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load settings, using defaults: %s", exc)
        return dict(_DEFAULTS)


def save(data: dict) -> dict:
    current = load()
    current.update({k: v for k, v in data.items() if k in _DEFAULTS})
    with tempfile.NamedTemporaryFile(
        mode="w", dir=SETTINGS_PATH.parent, suffix=".tmp", delete=False
    ) as f:
        json.dump(current, f, indent=2)
        tmp = f.name
    os.replace(tmp, SETTINGS_PATH)
    return current
