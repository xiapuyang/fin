import csv
import io
import re

from fastapi import APIRouter, Body, Depends, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from fin.database import get_db
from fin.models.user import MOCK_USER_ID
from fin.repositories.balance_account_sqlite import BalanceAccountSQLiteRepository
from fin.repositories.balance_item_sqlite import BalanceItemSQLiteRepository
from fin.repositories.balance_snapshot_sqlite import BalanceSnapshotSQLiteRepository
from fin.schemas.balance_account import (
    BalanceAccountCreate,
    BalanceAccountResponse,
    BalanceAccountUpdate,
)
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

_TS_FMT = "%Y-%m-%d %H:%M:%S"

# Notion page-ID → (snapshot_date, label) for the CSV import
_NOTION_SNAPSHOT_MAP = {
    "1819d2dbf46d8030acf2eccb7031086c": ("2025-01-20", "2025-01 初版"),
    "1ca9d2dbf46d80738856c8d9d79abfc2": ("2025-04-03", "2025-04 复盘"),
    "2759d2dbf46d80afa17ae3dd04f55527": ("2025-09-21", "2025-09 复盘"),
}

# item name → (parent_account_name, sub_account_name | None) for import auto-linking
_ITEM_NAME_TO_ACCOUNT: dict[str, tuple[str, str | None]] = {
    "招行存款": ("招商银行", "人民币"),
    "微众存款": ("微众银行", "人民币"),
    "CA GIC": ("BMO", "GIC"),
    "BMO": ("BMO", "Checking"),
    "QUEST 余额": ("UW", "QUEST"),
    "招商HK银行卡": ("招商香港", "港币活期"),
    "汇丰HK银行卡": ("汇丰银行", "港币活期"),
    "招行信用卡": ("招商信用卡", "人民币"),
    "中信信用卡": ("中信信用卡", "人民币"),
    "微信余额": ("微信", "零钱"),
    "支付宝余额": ("支付宝", "零钱"),
    "支付宝基金": ("支付宝", "基金帐户"),
    "IB股票": ("IB", "股票帐户"),
    "招商证券": ("招商证券", "股票帐户"),
    "陈兰存款": ("陈兰招商银行", "人民币"),
    "陈兰现金存款": ("陈兰微众银行", "人民币"),
    "ByteDance期权": ("期权", "字节跳动"),
    "Uvic预交学费": ("UW", "Tuition"),
    "中海房贷余额": ("房贷", "西安中海天谷时代"),
    "借出款项": ("外债", "借出"),
    "公积金": ("社保", "公积金"),
    "养老金": ("社保", "养老金"),
    "医保": ("社保", "医保"),
    "汽车": ("固定资产", "汽车"),
    "现金RMB": ("现金", "人民币"),
    "西安中海天谷时代": ("固定资产", "西安中海天谷时代"),
    "陈兰公积金": ("陈兰社保", "公积金"),
    "陈兰养老": ("陈兰社保", "养老"),
    "陈兰医保": ("陈兰社保", "医保"),
}


def _seed_accounts_if_empty(account_repo, user_id: int) -> int:
    """Create account hierarchy derived from _ITEM_NAME_TO_ACCOUNT if table is empty."""
    if account_repo.get_all(user_id):
        return 0
    # Build ordered parent→children structure preserving insertion order
    parents: dict[str, list[str]] = {}
    for parent, child in _ITEM_NAME_TO_ACCOUNT.values():
        parents.setdefault(parent, [])
        if child and child not in parents[parent]:
            parents[parent].append(child)
    created = 0
    for parent_name, children in parents.items():
        parent = account_repo.create(BalanceAccountCreate(name=parent_name), user_id)
        created += 1
        for child_name in children:
            account_repo.create(
                BalanceAccountCreate(name=child_name, parent_id=parent.id), user_id
            )
            created += 1
    return created


# ── Response helpers ──────────────────────────────────────────────────────────


def _account_response(m) -> BalanceAccountResponse:
    return BalanceAccountResponse(
        id=m.id,
        name=m.name,
        parent_id=m.parent_id,
        create_time=m.create_time.strftime(_TS_FMT),
        update_time=m.update_time.strftime(_TS_FMT),
    )


def _snapshot_response(m, item_count: int) -> BalanceSnapshotResponse:
    return BalanceSnapshotResponse(
        id=m.id,
        snapshot_date=m.snapshot_date,
        label=m.label,
        note=m.note,
        item_count=item_count,
        create_time=m.create_time.strftime(_TS_FMT),
        update_time=m.update_time.strftime(_TS_FMT),
    )


def _item_response(item, snapshot_date: str, account_map: dict) -> BalanceItemResponse:
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
        create_time=item.create_time.strftime(_TS_FMT),
        update_time=item.update_time.strftime(_TS_FMT),
    )


# ── Accounts ──────────────────────────────────────────────────────────────────


@router.get("/balance/accounts", response_model=list[BalanceAccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    return [
        _account_response(a)
        for a in BalanceAccountSQLiteRepository(db).get_all(MOCK_USER_ID)
    ]


@router.post(
    "/balance/accounts", response_model=BalanceAccountResponse, status_code=201
)
def create_account(data: BalanceAccountCreate, db: Session = Depends(get_db)):
    return _account_response(
        BalanceAccountSQLiteRepository(db).create(data, MOCK_USER_ID)
    )


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
        raise HTTPException(status_code=404, detail=str(e))
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

    new_snap = snap_repo.create(
        BalanceSnapshotCreate(
            snapshot_date=new_date or source.snapshot_date,
            label=new_label or source.label,
            note=source.note,
        ),
        MOCK_USER_ID,
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
    rows = item_repo.get_by_snapshot(data.snapshot_id, MOCK_USER_ID)
    snap_date = rows[0][1] if rows else ""
    account_map = rows[0][2] if rows else {}
    return _item_response(item, snap_date, account_map)


@router.put("/balance/items/{item_id}", response_model=BalanceItemResponse)
def update_item(item_id: int, data: BalanceItemUpdate, db: Session = Depends(get_db)):
    item_repo = BalanceItemSQLiteRepository(db)
    try:
        item = item_repo.update(item_id, data, MOCK_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    rows = item_repo.get_by_snapshot(item.snapshot_id, MOCK_USER_ID)
    snap_date = rows[0][1] if rows else ""
    account_map = rows[0][2] if rows else {}
    return _item_response(item, snap_date, account_map)


@router.delete("/balance/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    try:
        BalanceItemSQLiteRepository(db).delete(item_id, MOCK_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)


# ── Import ────────────────────────────────────────────────────────────────────


def _parse_import_amount(raw: str) -> float | None:
    s = raw.strip().replace("CN¥", "").replace(",", "").replace("¥", "")
    try:
        return float(s)
    except ValueError:
        return None


@router.post("/balance/import")
async def import_balance(file: UploadFile, db: Session = Depends(get_db)):
    """Import balance sheet items from a Notion CSV export."""
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    snap_repo = BalanceSnapshotSQLiteRepository(db)
    item_repo = BalanceItemSQLiteRepository(db)
    account_repo = BalanceAccountSQLiteRepository(db)
    accounts_seeded = _seed_accounts_if_empty(account_repo, MOCK_USER_ID)

    # Build account lookup: {name: account} and {parent_id: [children]}
    all_accounts = account_repo.get_all(MOCK_USER_ID)
    acct_by_name = {a.name: a for a in all_accounts}
    children_by_parent: dict[int, list] = {}
    for a in all_accounts:
        if a.parent_id:
            children_by_parent.setdefault(a.parent_id, []).append(a)

    def _resolve_account_ids(item_name: str) -> tuple[int | None, int | None]:
        entry = _ITEM_NAME_TO_ACCOUNT.get(item_name)
        if not entry:
            return None, None
        parent_name, child_name = entry
        parent = acct_by_name.get(parent_name)
        if not parent:
            return None, None
        sub = (
            next(
                (
                    c
                    for c in children_by_parent.get(parent.id, [])
                    if c.name == child_name
                ),
                None,
            )
            if child_name
            else None
        )
        return parent.id, (sub.id if sub else None)

    # Upsert snapshots by snapshot_date
    existing_snaps = {s.snapshot_date: s for s, _ in snap_repo.get_all(MOCK_USER_ID)}
    snapshots_created = 0
    snap_id_map: dict[str, int] = {}  # snapshot_date → id

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    def _ref_cell(row: dict) -> str:
        return " ".join(
            filter(
                None,
                [
                    row.get("关联资产负债表", ""),
                    row.get("﻿关联资产负债表", ""),
                    row.get("关联负债资产统计", ""),
                ],
            )
        )

    # Collect all needed snapshot dates
    needed_dates: set[str] = set()
    for row in rows:
        ref_cell = _ref_cell(row)
        page_ids = re.findall(r"[0-9a-f]{32}", ref_cell)
        for pid in page_ids:
            if pid in _NOTION_SNAPSHOT_MAP:
                date, _ = _NOTION_SNAPSHOT_MAP[pid]
                needed_dates.add(date)

    for date in sorted(needed_dates):
        if date in existing_snaps:
            snap_id_map[date] = existing_snaps[date].id
        else:
            label = next(
                (lbl for pid, (d, lbl) in _NOTION_SNAPSHOT_MAP.items() if d == date),
                date,
            )
            snap = snap_repo.create(
                BalanceSnapshotCreate(snapshot_date=date, label=label), MOCK_USER_ID
            )
            snap_id_map[date] = snap.id
            snapshots_created += 1

    # Existing items for dedup: {(snapshot_id, name, side)}
    existing_items = {
        (item.snapshot_id, item.name.strip(), item.side)
        for item, _, _ in item_repo.get_all(MOCK_USER_ID)
    }

    items_imported = 0
    skipped = []

    for i, row in enumerate(rows):
        name = (row.get("资产项", "") or "").strip()
        if not name:
            skipped.append({"row": i, "reason": "empty name"})
            continue

        amount = _parse_import_amount(row.get("金额", "") or "")
        if amount is None:
            skipped.append({"row": i, "name": name, "reason": "unparseable amount"})
            continue

        raw_side = (row.get("资产 OR 负债", "") or "").strip()
        if raw_side == "资产":
            side = "asset"
        elif raw_side == "负债":
            side = "liability"
        else:
            skipped.append(
                {"row": i, "name": name, "reason": f"unknown side: {raw_side!r}"}
            )
            continue

        raw_cat = (row.get("分类", "") or "").strip()
        from fin.schemas.balance_item import BALANCE_CATEGORIES

        category = (
            raw_cat
            if raw_cat in BALANCE_CATEGORIES
            else "其他贷款"
            if side == "liability"
            else "现金"
        )

        page_ids = re.findall(r"[0-9a-f]{32}", _ref_cell(row))
        matched_dates = sorted(
            _NOTION_SNAPSHOT_MAP[pid][0]
            for pid in page_ids
            if pid in _NOTION_SNAPSHOT_MAP
        )

        if not matched_dates:
            skipped.append(
                {"row": i, "name": name, "reason": "no recognized snapshot ref"}
            )
            continue

        account_id, sub_account_id = _resolve_account_ids(name)
        for date in matched_dates:
            snap_id = snap_id_map.get(date)
            if not snap_id:
                continue
            key = (snap_id, name, side)
            if key in existing_items:
                continue
            item_repo.create(
                BalanceItemCreate(
                    snapshot_id=snap_id,
                    name=name,
                    category=category,
                    side=side,
                    amount=amount,
                    currency="CNY",
                    account_id=account_id,
                    sub_account_id=sub_account_id,
                ),
                MOCK_USER_ID,
            )
            existing_items.add(key)
            items_imported += 1

    return {
        "snapshots_created": snapshots_created,
        "items_imported": items_imported,
        "accounts_seeded": accounts_seeded,
        "skipped": skipped,
    }
