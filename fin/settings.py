"""Persistent app settings stored in data/settings.json."""

import json

from fin.config import SETTINGS_PATH

_DEFAULTS = {
    "notify_email": "",
    "notify_enabled": True,
    "timezone": "America/Toronto",
    "rebalance": None,
}


def load() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULTS)
    try:
        return {**_DEFAULTS, **json.loads(SETTINGS_PATH.read_text())}
    except Exception:
        return dict(_DEFAULTS)


def save(data: dict) -> dict:
    current = load()
    current.update({k: v for k, v in data.items() if k in _DEFAULTS})
    SETTINGS_PATH.write_text(json.dumps(current, indent=2))
    return current
