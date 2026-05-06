import csv
import io
import json
import logging
import math
import re
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from fin import categories_store
from fin.database import get_db
from fin.ledger_categories import RECURRING_TYPE_MAP, SUBCATEGORY_MAP
from fin.models.ledger import LedgerModel
from fin.models.user import MOCK_USER_ID
from fin.repositories.ledger_sqlite import LedgerSQLiteRepository
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

# Matches "May 25, 2025 9:22 PM (EDT)" — capture up to AM/PM, discard timezone
_DATETIME_RE = re.compile(r"^(\w+ \d+, \d{4} \d+:\d+ [AP]M)")


def _resolve_category_name(cat_id: str) -> str:
    cat = categories_store.find(cat_id)
    return cat["name"] if cat else cat_id


def _ledger_response(e: LedgerModel, count: int | None = None) -> LedgerResponse:
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


def _parse_notion_amount(raw: str) -> float | None:
    """Parse 'CN¥1,174.00' → 1174.0. Returns None for zero or unparseable."""
    s = raw.strip().replace("CN¥", "").replace(",", "")
    try:
        val = float(s)
        return val if val > 0 else None
    except ValueError:
        return None


def _parse_notion_date(raw: str) -> str | None:
    """Parse Notion date fields to YYYY-MM-DD. Returns None on failure."""
    raw = raw.strip()
    if not raw:
        return None
    # Strip date range suffix like "November 1, 2022 → November 30, 2022"
    raw = raw.split("→")[0].strip()
    m = _DATETIME_RE.match(raw)
    if m:
        raw = m.group(1)
        try:
            return datetime.strptime(raw, "%B %d, %Y %I:%M %p").strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.strptime(raw, "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_expiry_date(raw: str) -> str | None:
    """Parse '2025/09/01' → '2025-09-01'."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y/%m/%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_notion_row(row: dict) -> tuple[LedgerCreate | None, str]:
    """Parse one Notion expense CSV row. Returns (LedgerCreate, '') or (None, reason)."""
    name = row.get("Name", "").strip()
    if not name:
        return None, "empty name"

    amount = _parse_notion_amount(row.get("金额", ""))
    if amount is None:
        return None, f"zero or unparseable amount: {row.get('金额', '')!r}"

    date_str = _parse_notion_date(row.get("消费日期", ""))
    if date_str is None:
        return None, f"unparseable date: {row.get('消费日期', '')!r}"

    raw_sub = row.get("分类", "").strip()
    category = SUBCATEGORY_MAP.get(raw_sub, "0019")

    raw_type = row.get("消费类型", "").strip()
    recurring_type = RECURRING_TYPE_MAP.get(raw_type)

    is_expired = row.get("是否过期", "").strip() == "Yes"
    expiry_date = _parse_expiry_date(row.get("过期时间", ""))

    note = row.get("Text", "").strip() or None

    return LedgerCreate(
        direction="expense",
        name=name,
        date=date_str,
        amount=amount,
        currency="CNY",
        category=category,
        orig_category=raw_sub or None,
        subcategory=None,
        recurring_type=recurring_type,
        is_expired=is_expired,
        expiry_date=expiry_date,
        note=note,
    ), ""


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
    subcategory: str = Query(...),
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
    display_currency: str = Query(default="CNY"),
    db: Session = Depends(get_db),
):
    parsed_fx = json.loads(fx_rates) if fx_rates else None
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


# ── Import ───────────────────────────────────────────────────────────────────


@router.post("/ledger/import")
async def import_ledger(file: UploadFile, db: Session = Depends(get_db)):
    """Import expense records from a Notion CSV export."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    valid: list[LedgerCreate] = []
    skipped: list[dict] = []

    for i, row in enumerate(reader):
        entry, reason = _parse_notion_row(row)
        if entry is None:
            skipped.append({"row": i, "name": row.get("Name", ""), "reason": reason})
        else:
            valid.append(entry)

    repo = LedgerSQLiteRepository(db)
    imported = repo.bulk_create(valid, MOCK_USER_ID)
    logger.info(
        "Ledger CSV import: %d imported, %d skipped", len(imported), len(skipped)
    )
    return {"imported": len(imported), "skipped": skipped}


# ── Backfill ─────────────────────────────────────────────────────────────────


@router.post("/ledger/backfill-amounts")
def backfill_amounts(
    fx_rates: dict = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Compute amounts_json for rows where it is NULL or missing currencies."""
    currencies = ["CNY", "USD", "CAD", "HKD"]
    repo = LedgerSQLiteRepository(db)
    updated = repo.backfill_amounts_json(MOCK_USER_ID, fx_rates, currencies)
    logger.info("Backfilled amounts_json for %d ledger rows", updated)
    return {"updated": updated}
