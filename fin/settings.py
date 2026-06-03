"""Persistent app settings stored in data/settings.json."""

import json
import logging
import os
import tempfile

from fin.config import SETTINGS_PATH

logger = logging.getLogger(__name__)

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
    "language": "en",
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
