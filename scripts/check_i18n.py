"""Report i18n key coverage — keys in en.json missing from zh.json and vice versa."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
EN = ROOT / "config" / "i18n" / "en.json"
ZH = ROOT / "config" / "i18n" / "zh.json"


def main():
    """Compare en.json and zh.json key sets and report drift.

    Returns:
        Exit code: 0 if locale files are consistent, 1 if any drift,
        2 if a locale file is missing or unreadable.
    """
    try:
        en = json.loads(EN.read_text(encoding="utf-8"))
        zh = json.loads(ZH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        print(f"[ERROR] locale file not found: {exc.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"[ERROR] invalid JSON in locale file: {exc}", file=sys.stderr)
        return 2

    en_keys = set(en)
    zh_keys = set(zh)

    missing_zh = sorted(en_keys - zh_keys)
    missing_en = sorted(zh_keys - en_keys)
    untranslated = sorted(k for k in en_keys & zh_keys if en[k] == k and zh[k] == k)

    print(f"en.json: {len(en_keys)} keys")
    print(f"zh.json: {len(zh_keys)} keys")

    if missing_zh:
        print(f"\n[MISSING from zh.json] ({len(missing_zh)}):")
        for k in missing_zh:
            print(f"  {k!r}: {en[k]!r}")

    if missing_en:
        print(f"\n[MISSING from en.json] ({len(missing_en)}):")
        for k in missing_en:
            print(f"  {k!r}: {zh[k]!r}")

    if untranslated:
        print(
            f"\n[UNTRANSLATED — key used as value in both locales] ({len(untranslated)}):"
        )
        for k in untranslated:
            print(f"  {k!r}")

    if not missing_zh and not missing_en and not untranslated:
        print("\nAll keys consistent.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
