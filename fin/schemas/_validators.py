import datetime
import re
from typing import Optional

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(v: str) -> str:
    """Validate a required YYYY-MM-DD calendar date.

    Args:
        v: Candidate date string.

    Returns:
        The same string, unchanged, on success.

    Raises:
        ValueError: If `v` is not a YYYY-MM-DD format match or names a
            calendar-invalid date (e.g. ``2024-13-45`` or ``2023-02-29``).
    """
    if not _DATE_RE.match(v):
        raise ValueError("must be a date in YYYY-MM-DD format")
    try:
        datetime.date.fromisoformat(v)
    except ValueError as exc:
        raise ValueError("must be a valid calendar date in YYYY-MM-DD format") from exc
    return v


def validate_optional_date(v: Optional[str]) -> Optional[str]:
    """Validate an optional YYYY-MM-DD calendar date, coercing ``""`` to ``None``.

    Args:
        v: Candidate date string, or ``None``.

    Returns:
        ``None`` when `v` is ``None`` or an empty string; otherwise the
        validated date string unchanged.

    Raises:
        ValueError: If `v` is a non-empty string that is not a YYYY-MM-DD
            format match or names a calendar-invalid date.
    """
    if v is None or v == "":
        return None
    if not _DATE_RE.match(v):
        raise ValueError("must be a date in YYYY-MM-DD format")
    try:
        datetime.date.fromisoformat(v)
    except ValueError as exc:
        raise ValueError("must be a valid calendar date in YYYY-MM-DD format") from exc
    return v


def validate_nonempty(v: str) -> str:
    """Validate that a string is non-empty after whitespace stripping.

    Args:
        v: Candidate string.

    Returns:
        The same string, unchanged, on success (leading/trailing whitespace
        is **not** stripped from the returned value).

    Raises:
        ValueError: If `v` is empty or whitespace-only.
    """
    if not v.strip():
        raise ValueError("must not be empty")
    return v
