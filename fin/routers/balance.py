import json

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fin.config import DATA_DIR, TS_FMT
from fin.database import get_db
from fin.models.balance_account import BalanceAccountModel
from fin.models.balance_item import BalanceItemModel
from fin.models.balance_snapshot import BalanceSnapshotModel
from fin.models.user import MOCK_USER_ID
from fin.repositories.balance_account_sqlite import BalanceAccountSQLiteRepository
from fin.repositories.balance_item_sqlite import BalanceItemSQLiteRepository
from fin.repositories.balance_snapshot_sqlite import BalanceSnapshotSQLiteRepository
from fin.schemas.balance_account import (
    BalanceAccountBulkItem,
    BalanceAccountCreate,
    BalanceAccountResponse,
    BalanceAccountUpdate,
)
from fin.schemas.bulk import BulkResponse
from fin.schemas.balance_item import (
    BalanceItemCreate,
    BalanceItemResponse,
    BalanceItemUpdate,
)
from fin.schemas.balance_snapshot import (
    BalanceSnapshotCreate,
    BalanceSnapshotResponse,
    BalanceSnapshotUpdate,
)

router = APIRouter(prefix="/api")

_ACCOUNT_COLORS_PATH = DATA_DIR / "account_colors.json"


# ── Response helpers ──────────────────────────────────────────────────────────


def _account_response(m: BalanceAccountModel) -> BalanceAccountResponse:
    return BalanceAccountResponse(
        id=m.id,
        name=m.name,
        parent_id=m.parent_id,
        create_time=m.create_time.strftime(TS_FMT),
        update_time=m.update_time.strftime(TS_FMT),
    )


def _snapshot_response(
    m: BalanceSnapshotModel, item_count: int
) -> BalanceSnapshotResponse:
    return BalanceSnapshotResponse(
        id=m.id,
        snapshot_date=m.snapshot_date,
        label=m.label,
        note=m.note,
        item_count=item_count,
        create_time=m.create_time.strftime(TS_FMT),
        update_time=m.update_time.strftime(TS_FMT),
    )


def _item_response(
    item: BalanceItemModel, snapshot_date: str, account_map: dict[int, str]
) -> BalanceItemResponse:
    return BalanceItemResponse(
        id=item.id,
        snapshot_id=item.snapshot_id,
        snapshot_date=snapshot_date,
        account_id=item.account_id,
        sub_account_id=item.sub_account_id,
        account_name=account_map.get(item.account_id) if item.account_id else None,
        sub_account_name=account_map.get(item.sub_account_id)
        if item.sub_account_id
        else None,
        category=item.category,
        side=item.side,
        name=item.name,
        amount=item.amount,
        currency=item.currency,
        note=item.note,
        price=item.price,
        quantity=item.quantity,
        start_date=item.start_date,
        end_date=item.end_date,
        interest_rate=item.interest_rate,
        monthly_payment=item.monthly_payment,
        create_time=item.create_time.strftime(TS_FMT),
        update_time=item.update_time.strftime(TS_FMT),
    )


# ── Accounts ──────────────────────────────────────────────────────────────────


@router.get("/balance/accounts", response_model=list[BalanceAccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    return [
        _account_response(a)
        for a in BalanceAccountSQLiteRepository(db).get_all(MOCK_USER_ID)
    ]


@router.get("/balance/account-colors")
def get_account_colors() -> dict[str, str]:
    """Account-name → hex color overrides loaded from a gitignored file.

    Returns {} when the file is missing or malformed so the UI falls back to
    its built-in category palette plus a gray default per account.
    """
    if not _ACCOUNT_COLORS_PATH.exists():
        return {}
    try:
        data = json.loads(_ACCOUNT_COLORS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


@router.post(
    "/balance/accounts", response_model=BalanceAccountResponse, status_code=201
)
def create_account(data: BalanceAccountCreate, db: Session = Depends(get_db)):
    return _account_response(
        BalanceAccountSQLiteRepository(db).create(data, MOCK_USER_ID)
    )


@router.post("/balance/accounts/bulk", response_model=BulkResponse, status_code=201)
def bulk_create_balance_accounts(
    items: list[BalanceAccountBulkItem],
    db: Session = Depends(get_db),
) -> BulkResponse:
    """Bulk-create balance accounts; resolves parents by name.

    Two-phase insert in one transaction: root accounts first, then children
    whose `parent_name` is resolved against the union of existing roots and
    just-created roots. Unknown parent names abort the whole batch with 400.

    Dedup key is `(user_id, name, parent_id)`; duplicates are counted as
    skipped, not errors.
    """
    repo = BalanceAccountSQLiteRepository(db)
    try:
        created, skipped = repo.bulk_create_with_parent_names(
            items, user_id=MOCK_USER_ID
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return BulkResponse(created=created, skipped=skipped)


@router.put("/balance/accounts/{account_id}", response_model=BalanceAccountResponse)
def update_account(
    account_id: int, data: BalanceAccountUpdate, db: Session = Depends(get_db)
):
    try:
        return _account_response(
            BalanceAccountSQLiteRepository(db).update(account_id, data, MOCK_USER_ID)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/balance/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    try:
        BalanceAccountSQLiteRepository(db).delete(account_id, MOCK_USER_ID)
    except ValueError as e:
        msg = str(e)
        status = 409 if "child accounts" in msg else 404
        raise HTTPException(status_code=status, detail=msg)
    return Response(status_code=204)


# ── Snapshots ─────────────────────────────────────────────────────────────────


@router.get("/balance/snapshots", response_model=list[BalanceSnapshotResponse])
def list_snapshots(db: Session = Depends(get_db)):
    return [
        _snapshot_response(snap, count)
        for snap, count in BalanceSnapshotSQLiteRepository(db).get_all(MOCK_USER_ID)
    ]


@router.post(
    "/balance/snapshots", response_model=BalanceSnapshotResponse, status_code=201
)
def create_snapshot(data: BalanceSnapshotCreate, db: Session = Depends(get_db)):
    snap = BalanceSnapshotSQLiteRepository(db).create(data, MOCK_USER_ID)
    return _snapshot_response(snap, 0)


@router.put("/balance/snapshots/{snapshot_id}", response_model=BalanceSnapshotResponse)
def update_snapshot(
    snapshot_id: int, data: BalanceSnapshotUpdate, db: Session = Depends(get_db)
):
    try:
        snap_repo = BalanceSnapshotSQLiteRepository(db)
        snap = snap_repo.update(snapshot_id, data, MOCK_USER_ID)
        rows = snap_repo.get_all(MOCK_USER_ID)
        count = next((c for s, c in rows if s.id == snapshot_id), 0)
        return _snapshot_response(snap, count)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/balance/snapshots/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    try:
        BalanceSnapshotSQLiteRepository(db).delete(snapshot_id, MOCK_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)


@router.post(
    "/balance/snapshots/{snapshot_id}/copy",
    response_model=BalanceSnapshotResponse,
    status_code=201,
)
def copy_snapshot(
    snapshot_id: int,
    new_label: str | None = Body(default=None),
    new_date: str | None = Body(default=None),
    db: Session = Depends(get_db),
):
    snap_repo = BalanceSnapshotSQLiteRepository(db)
    item_repo = BalanceItemSQLiteRepository(db)
    try:
        source = snap_repo.get_by_id(snapshot_id, MOCK_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        new_snap = snap_repo.create(
            BalanceSnapshotCreate(
                snapshot_date=new_date or source.snapshot_date,
                label=new_label if new_label is not None else f"{source.label} (副本)",
                note=source.note,
            ),
            MOCK_USER_ID,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="A snapshot with this label and date already exists"
        )
    count = item_repo.copy_snapshot(snapshot_id, new_snap.id, MOCK_USER_ID)
    return _snapshot_response(new_snap, count)


# ── Items ─────────────────────────────────────────────────────────────────────


@router.get(
    "/balance/snapshots/{snapshot_id}/items", response_model=list[BalanceItemResponse]
)
def list_snapshot_items(snapshot_id: int, db: Session = Depends(get_db)):
    return [
        _item_response(item, snap_date, account_map)
        for item, snap_date, account_map in BalanceItemSQLiteRepository(
            db
        ).get_by_snapshot(snapshot_id, MOCK_USER_ID)
    ]


@router.get("/balance/items", response_model=list[BalanceItemResponse])
def list_all_items(db: Session = Depends(get_db)):
    return [
        _item_response(item, snap_date, account_map)
        for item, snap_date, account_map in BalanceItemSQLiteRepository(db).get_all(
            MOCK_USER_ID
        )
    ]


@router.post("/balance/items", response_model=BalanceItemResponse, status_code=201)
def create_item(data: BalanceItemCreate, db: Session = Depends(get_db)):
    item_repo = BalanceItemSQLiteRepository(db)
    item = item_repo.create(data, MOCK_USER_ID)
    snap = (
        db.query(BalanceSnapshotModel)
        .filter(BalanceSnapshotModel.id == data.snapshot_id)
        .first()
    )
    snap_date = snap.snapshot_date if snap else ""
    rows = item_repo.get_by_snapshot(data.snapshot_id, MOCK_USER_ID)
    account_map = rows[0][2] if rows else {}
    return _item_response(item, snap_date, account_map)


@router.post("/balance/items/bulk", response_model=BulkResponse, status_code=201)
def bulk_create_balance_items(
    items: list[BalanceItemCreate],
    db: Session = Depends(get_db),
) -> BulkResponse:
    """Bulk-create balance items. All-or-nothing on validation; duplicates skipped.

    Each item must carry a valid `snapshot_id` (Pydantic enforces presence at
    422; the dedup key is `(snapshot_id, name, side, category)`). The endpoint
    does NOT resolve snapshots by date — that lives in the fin-import skill.
    """
    repo = BalanceItemSQLiteRepository(db)
    created, skipped = repo.bulk_create(items, user_id=MOCK_USER_ID)
    return BulkResponse(created=len(created), skipped=skipped)


@router.put("/balance/items/{item_id}", response_model=BalanceItemResponse)
def update_item(item_id: int, data: BalanceItemUpdate, db: Session = Depends(get_db)):
    item_repo = BalanceItemSQLiteRepository(db)
    try:
        item = item_repo.update(item_id, data, MOCK_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    snap = (
        db.query(BalanceSnapshotModel)
        .filter(BalanceSnapshotModel.id == item.snapshot_id)
        .first()
    )
    snap_date = snap.snapshot_date if snap else ""
    rows = item_repo.get_by_snapshot(item.snapshot_id, MOCK_USER_ID)
    account_map = rows[0][2] if rows else {}
    return _item_response(item, snap_date, account_map)


@router.delete("/balance/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    try:
        BalanceItemSQLiteRepository(db).delete(item_id, MOCK_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)
