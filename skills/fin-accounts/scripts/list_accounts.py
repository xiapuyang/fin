"""Fetch all balance accounts from fin and print as JSON.

Usage:
    python list_accounts.py
    FIN_API_URL=http://localhost:18888 python list_accounts.py
"""

import json
import sys

import requests

from _fin_url import resolve_base


def main() -> int:
    base = resolve_base()
    url = base + "/api/balance/accounts"
    try:
        r = requests.get(url, timeout=10)
    except requests.ConnectionError:
        print(f"ERROR: could not reach fin at {base}", file=sys.stderr)
        return 1
    if r.status_code >= 400:
        print(f"ERROR: {r.status_code}: {r.text}", file=sys.stderr)
        return 1
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
