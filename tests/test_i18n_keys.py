"""Regression test: en.json and zh.json must keep parity.

Mirrors scripts/check_i18n.py so locale drift fails CI instead of shipping silently.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
EN_PATH = ROOT / "config" / "i18n" / "en.json"
ZH_PATH = ROOT / "config" / "i18n" / "zh.json"


def _load_locale(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_en_and_zh_have_identical_key_sets():
    en = _load_locale(EN_PATH)
    zh = _load_locale(ZH_PATH)
    missing_in_zh = sorted(set(en) - set(zh))
    missing_in_en = sorted(set(zh) - set(en))
    assert not missing_in_zh, f"keys in en.json missing from zh.json: {missing_in_zh}"
    assert not missing_in_en, f"keys in zh.json missing from en.json: {missing_in_en}"


def test_no_keys_used_as_their_own_value():
    """A key whose value equals itself in both locales is unset (placeholder)."""
    en = _load_locale(EN_PATH)
    zh = _load_locale(ZH_PATH)
    untranslated = sorted(k for k in en.keys() & zh.keys() if en[k] == k and zh[k] == k)
    assert not untranslated, (
        f"keys used as their own value (untranslated): {untranslated}"
    )
