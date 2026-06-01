"""Shared utilities for fin-import and fin-accounts skill scripts."""

import json
import time
from pathlib import Path


def _load_rows(arg: str) -> list[dict]:
    """Accept either an inline JSON list/object or a file path.

    Args:
        arg: Inline JSON string (starting with '[' or '{') or a file path.

    Returns:
        Parsed list of row dicts.
    """
    stripped = arg.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return json.loads(arg)
    return json.loads(Path(arg).read_text())


def _err(reason: str, payload=None, prefix: str = "fin-import") -> dict:
    """Write an error payload to /tmp and return a BulkResponse-shaped error dict.

    Args:
        reason: Human-readable error description.
        payload: Optional request payload to persist alongside the reason.
        prefix: Filename prefix for the error file (default: fin-import).

    Returns:
        Dict with created=0, skipped=0, and a single error entry pointing to
        the written file.
    """
    ts = int(time.time())
    err_path = Path(f"/tmp/{prefix}-error-{ts}.json")
    err_path.write_text(
        json.dumps(
            {"reason": reason, "payload": payload},
            indent=2,
            ensure_ascii=False,
        )
    )
    return {
        "created": 0,
        "skipped": 0,
        "errors": [{"reason": reason, "details": str(err_path)}],
    }
