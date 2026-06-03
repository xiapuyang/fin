"""Persistent app settings stored in data/settings.json."""

import json
import locale
import logging
import os
import sys
import tempfile

from fin.config import APP_CONFIG, SETTINGS_PATH

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


# Static defaults come from config/app.json so frontend + backend share one source.
# `language` is dynamic (depends on OS) so it's layered on at load time.
_STATIC_DEFAULTS = APP_CONFIG.get("settings_defaults", {})


def _defaults() -> dict:
    """Return the full default settings dict, including dynamic OS-detected language."""
    return {**_STATIC_DEFAULTS, "language": _detect_os_locale()}


def load() -> dict:
    defaults = _defaults()
    if not SETTINGS_PATH.exists():
        return defaults
    try:
        return {**defaults, **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load settings, using defaults: %s", exc)
        return defaults


def save(data: dict) -> dict:
    current = load()
    allowed = set(_defaults().keys())
    current.update({k: v for k, v in data.items() if k in allowed})
    with tempfile.NamedTemporaryFile(
        mode="w", dir=SETTINGS_PATH.parent, suffix=".tmp", delete=False
    ) as f:
        json.dump(current, f, indent=2)
        tmp = f.name
    os.replace(tmp, SETTINGS_PATH)
    return current
