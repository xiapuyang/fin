"""Python-side i18n: shared translation lookup for launcher, notifiers, etc.

Mirrors `frontend/src/i18n.jsx`. Reads `config/i18n/{lang}.json`. Language
resolution falls through: explicit `lang=` argument → `settings.json["language"]`
→ OS UI locale → English. Cache is invalidated by file mtime so editing a JSON
on disk is picked up on the next `t()` call — no app restart needed.

Usage:
    from fin.i18n import t
    t("launcher.update_found", tag="v0.2.0", current="0.1.0")
"""

from __future__ import annotations

import json
import logging
from threading import Lock
from typing import Any, Optional

from fin.config import APP_CONFIG, I18N_DIR

logger = logging.getLogger(__name__)

_i18n_cfg = APP_CONFIG.get("i18n", {})
DEFAULT_LANG: str = _i18n_cfg.get("default_lang", "en")
SUPPORTED_LANGS: tuple[str, ...] = tuple(_i18n_cfg.get("supported_langs", ["en", "zh"]))

_cache: dict[str, dict[str, str]] = {}
_mtime: dict[str, float] = {}
_lock = Lock()


def _resolve_lang() -> str:
    """Pick the active language: settings.json → OS locale → DEFAULT_LANG."""
    try:
        from fin import settings as _settings

        lang = (_settings.load().get("language") or "").strip().lower()
        if lang in SUPPORTED_LANGS:
            return lang
    except Exception as exc:  # pragma: no cover — settings missing on first launch
        logger.debug("i18n: settings.json unavailable (%s)", exc)

    try:
        from fin.settings import _detect_os_locale

        os_lang = _detect_os_locale()
        if os_lang in SUPPORTED_LANGS:
            return os_lang
    except Exception as exc:  # pragma: no cover
        logger.debug("i18n: OS locale detection failed (%s)", exc)

    return DEFAULT_LANG


def _load(lang: str) -> dict[str, str]:
    """Return cached translations for `lang`, reloading if the file changed."""
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        return {}

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _cache.get(lang, {})

    with _lock:
        if _mtime.get(lang) == mtime and lang in _cache:
            return _cache[lang]
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("i18n: failed to load %s: %s", path, exc)
            return _cache.get(lang, {})
        _cache[lang] = data
        _mtime[lang] = mtime
        return data


def t(key: str, lang: Optional[str] = None, **fmt: Any) -> str:
    """Translate `key` into the active language.

    Lookup order: active locale → English → bare key. `**fmt` is passed to
    str.format(); a malformed template returns the unformatted string.
    """
    active = (lang or _resolve_lang()).lower()
    value = _load(active).get(key)
    if value is None and active != DEFAULT_LANG:
        value = _load(DEFAULT_LANG).get(key)
    if value is None:
        return key
    if fmt:
        try:
            return value.format(**fmt)
        except (KeyError, IndexError, ValueError) as exc:
            logger.debug("i18n: format failed for %s: %s", key, exc)
            return value
    return value


def reload() -> None:
    """Drop all caches; next t() call reloads every file from disk."""
    with _lock:
        _cache.clear()
        _mtime.clear()
