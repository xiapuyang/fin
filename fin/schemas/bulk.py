"""Shared response schema for all /bulk endpoints."""

from pydantic import BaseModel


class BulkResponse(BaseModel):
    """Returned by every /api/{domain}/bulk endpoint.

    Insert-only: duplicates are pre-filtered before insert (counted in
    `skipped`). Validation failures → 422 before any insert. Any unexpected
    DB error → 500 with full rollback. `errors` stays empty on success.
    """

    created: int
    skipped: int
    errors: list[dict] = []
