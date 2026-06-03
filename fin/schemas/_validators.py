import re
from typing import Optional

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(v: str) -> str:
    if not _DATE_RE.match(v):
        raise ValueError("must be a date in YYYY-MM-DD format")
    return v


def validate_optional_date(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not _DATE_RE.match(v):
        raise ValueError("must be a date in YYYY-MM-DD format")
    return v


def validate_nonempty(v: str) -> str:
    if not v.strip():
        raise ValueError("must not be empty")
    return v
