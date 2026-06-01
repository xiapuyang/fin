"""Shared URL resolver for fin skill scripts.

Decision tree (in order):
  1. FIN_API_URL env var → use as-is
  2. ~/.fin-dev exists   → always use dev port 18888
  3. Both ports open     → refuse (ambiguous, would silently hit wrong data)
  4. Default             → prod port 8888
"""

import os
import socket
import sys
from pathlib import Path

PROD_PORT = 8888
DEV_PORT = 18888


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _decide() -> tuple[str, str]:
    explicit = os.environ.get("FIN_API_URL")
    if explicit:
        return explicit, "FIN_API_URL env"
    if (Path.home() / ".fin-dev").exists():
        return f"http://127.0.0.1:{DEV_PORT}", "~/.fin-dev present → dev"
    if _port_open(PROD_PORT) and _port_open(DEV_PORT):
        raise SystemExit(
            f"REFUSED: both prod ({PROD_PORT}) and dev ({DEV_PORT}) fin servers "
            "are running but ~/.fin-dev is missing. Either `touch ~/.fin-dev` to "
            "lock to dev, stop one server, or set FIN_API_URL explicitly."
        )
    return f"http://localhost:{PROD_PORT}", "default → prod"


def resolve_base() -> str:
    base, reason = _decide()
    print(f"[fin] → {base}  ({reason})", file=sys.stderr)
    return base


if __name__ == "__main__":
    resolve_base()
