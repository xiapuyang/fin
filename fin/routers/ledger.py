import json
import logging
import math
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import Field
from sqlalchemy.orm import Session

from fin import categories_store
from fin.config import BULK_MAX_ITEMS, SUPPORTED_CURRENCIES
from fin.database import get_db
from fin.models.ledger import LedgerModel
from fin.models.user import MOCK_USER_ID
from fin.repositories.ledger_sqlite import LedgerSQLiteRepository
from fin.schemas.bulk import BulkResponse
from fin.schemas.ledger import (
    LedgerCreate,
    LedgerListResponse,
    LedgerResponse,
    LedgerStatsResponse,
    LedgerUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_TS_FMT = "%Y-%m-%d %H:%M:%S"
_CCY_PATTERN = "^(" + "|".join(SUPPORTED_CURRENCIES) + ")$"


def _resolve_category_name(cat_id: str) -> str:
    """Look up a category ID's display name.

    Args:
        cat_id: Category ID string (e.g. '0001').

    Returns:
        Human-readable name, or cat_id unchanged if not found.
    """
    cat = categories_store.find(cat_id)
    return cat["name"] if cat else cat_id


def _ledger_response(e: LedgerModel, count: int | None = None) -> LedgerResponse:
    """Convert a LedgerModel ORM instance to a LedgerResponse schema.

    Args:
        e: ORM model instance.
        count: Optional occurrence count for recurring entries.

    Returns:
        LedgerResponse schema instance.
    """
    return LedgerResponse(
        id=e.id,
        direction=e.direction,
        name=e.name,
        date=e.date,
        amount=e.amount,
        currency=e.currency,
        category=e.category,
        category_name=_resolve_category_name(e.category),
        orig_category=e.orig_category,
        subcategory=e.subcategory,
        recurring_type=e.recurring_type,
        is_expired=e.is_expired,
        expiry_date=e.expiry_date,
        note=e.note,
        create_time=e.create_time.strftime(_TS_FMT),
        update_time=e.update_time.strftime(_TS_FMT),
        count=count,
    )


# ── List + CRUD ──────────────────────────────────────────────────────────────


@router.get("/ledger", response_model=LedgerListResponse)
def list_ledger(
    direction: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    repo = LedgerSQLiteRepository(db)
    items, total = repo.get_list(
        MOCK_USER_ID,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        category=category,
        search=search,
        page=page,
        page_size=page_size,
    )
    pages = math.ceil(total / page_size) if total else 1
    return LedgerListResponse(
        items=[_ledger_response(e) for e in items],
        total=total,
        page=page,
        pages=pages,
    )


@router.post("/ledger", response_model=LedgerResponse, status_code=201)
def create_ledger(data: LedgerCreate, db: Session = Depends(get_db)):
    return _ledger_response(LedgerSQLiteRepository(db).create(data, MOCK_USER_ID))


@router.post("/ledger/bulk", response_model=BulkResponse, status_code=201)
def bulk_create_ledger(
    items: Annotated[list[LedgerCreate], Field(max_length=BULK_MAX_ITEMS)],
    db: Session = Depends(get_db),
):
    """Bulk-create ledger entries. All-or-nothing on validation; duplicates skipped.

    Reuses the existing `bulk_create()` repo method which dedups on the
    `uq_ledger_dedup` unique constraint `(user_id, direction, name, date,
    amount)` via SQLite `ON CONFLICT DO NOTHING`. Validation errors on any
    item short-circuit with 422 before any insert (FastAPI handles this via
    the `list[LedgerCreate]` body annotation).
    """
    repo = LedgerSQLiteRepository(db)
    created = repo.bulk_create(items, MOCK_USER_ID)
    return BulkResponse(created=len(created), skipped=len(items) - len(created))


@router.put("/ledger/{entry_id}", response_model=LedgerResponse)
def update_ledger(entry_id: int, data: LedgerUpdate, db: Session = Depends(get_db)):
    try:
        return _ledger_response(
            LedgerSQLiteRepository(db).update(entry_id, data, MOCK_USER_ID)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/ledger/{entry_id}", status_code=204)
def delete_ledger(entry_id: int, db: Session = Depends(get_db)):
    LedgerSQLiteRepository(db).delete(entry_id, MOCK_USER_ID)
    return Response(status_code=204)


# ── Years ────────────────────────────────────────────────────────────────────


@router.get("/ledger/years", response_model=list[int])
def ledger_years(db: Session = Depends(get_db)):
    return LedgerSQLiteRepository(db).get_years(MOCK_USER_ID)


# ── Recurring ────────────────────────────────────────────────────────────────


@router.get("/ledger/recurring", response_model=list[LedgerResponse])
def list_recurring(
    include_expired: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    repo = LedgerSQLiteRepository(db)
    return [
        _ledger_response(e, count=c)
        for e, c in repo.get_recurring(MOCK_USER_ID, include_expired=include_expired)
    ]


@router.get("/ledger/recurring/series", response_model=list[LedgerResponse])
def list_recurring_series(
    recurring_type: str = Query(...),
    category: str = Query(...),
    subcategory: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    repo = LedgerSQLiteRepository(db)
    rows = repo.get_series(MOCK_USER_ID, recurring_type, category, subcategory)
    return [_ledger_response(r) for r in rows]


# ── Stats ────────────────────────────────────────────────────────────────────


@router.get("/ledger/stats", response_model=LedgerStatsResponse)
def ledger_stats(
    time_range: str | None = Query(default=None, pattern="^(7d|30d|1y|all)$"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    category: str | None = Query(default=None),
    fx_rates: str | None = Query(default=None),
    display_currency: str = Query(default="CNY", pattern=_CCY_PATTERN),
    db: Session = Depends(get_db),
):
    if fx_rates:
        try:
            parsed_fx = json.loads(fx_rates)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid fx_rates JSON")
    else:
        parsed_fx = None
    repo = LedgerSQLiteRepository(db)
    data = repo.get_stats(
        MOCK_USER_ID,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        category=category,
        fx_rates=parsed_fx,
        display_currency=display_currency,
    )
    return LedgerStatsResponse(
        bars=data["bars"],
        pie=data["pie"],
        summary=data["summary"],
    )


# ── Backfill ─────────────────────────────────────────────────────────────────


@router.post("/ledger/backfill-amounts")
def backfill_amounts(
    fx_rates: dict = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Compute amounts_json for rows where it is NULL or missing currencies."""
    currencies = SUPPORTED_CURRENCIES
    repo = LedgerSQLiteRepository(db)
    updated = repo.backfill_amounts_json(MOCK_USER_ID, fx_rates, currencies)
    logger.info("Backfilled amounts_json for %d ledger rows", updated)
    return {"updated": updated}
