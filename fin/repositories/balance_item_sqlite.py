from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.balance_item import BalanceItemModel
from fin.schemas.balance_item import BalanceItemCreate, BalanceItemUpdate


def _build_account_map(db: Session, user_id: int) -> dict[int, str]:
    """Return {account_id: name} for all balance_accounts of this user."""
    from fin.models.balance_account import BalanceAccountModel

    rows = (
        db.query(BalanceAccountModel.id, BalanceAccountModel.name)
        .filter(BalanceAccountModel.user_id == user_id)
        .all()
    )
    return {r.id: r.name for r in rows}


class BalanceItemSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(
        self, user_id: int
    ) -> list[tuple[BalanceItemModel, str, dict[int, str]]]:
        """Return (item, snapshot_date, account_map) — snapshot_date denormalized."""
        from fin.models.balance_snapshot import BalanceSnapshotModel

        snaps = (
            self._db.query(BalanceSnapshotModel.id, BalanceSnapshotModel.snapshot_date)
            .filter(BalanceSnapshotModel.user_id == user_id)
            .all()
        )
        snap_date_map = {s.id: s.snapshot_date for s in snaps}
        rows = (
            self._db.query(BalanceItemModel)
            .filter(BalanceItemModel.user_id == user_id)
            .order_by(BalanceItemModel.snapshot_id, BalanceItemModel.id)
            .all()
        )
        account_map = _build_account_map(self._db, user_id)
        return [
            (item, snap_date_map.get(item.snapshot_id, ""), account_map)
            for item in rows
        ]

    def get_by_snapshot(
        self, snapshot_id: int, user_id: int
    ) -> list[tuple[BalanceItemModel, str, dict]]:
        from fin.models.balance_snapshot import BalanceSnapshotModel

        snap = (
            self._db.query(BalanceSnapshotModel.snapshot_date)
            .filter(
                BalanceSnapshotModel.id == snapshot_id,
                BalanceSnapshotModel.user_id == user_id,
            )
            .scalar()
        )
        snap_date = snap or ""
        rows = (
            self._db.query(BalanceItemModel)
            .filter(
                BalanceItemModel.snapshot_id == snapshot_id,
                BalanceItemModel.user_id == user_id,
            )
            .order_by(BalanceItemModel.id)
            .all()
        )
        account_map = _build_account_map(self._db, user_id)
        return [(item, snap_date, account_map) for item in rows]

    def get_by_id(self, item_id: int, user_id: int) -> BalanceItemModel:
        row = (
            self._db.query(BalanceItemModel)
            .filter(
                BalanceItemModel.id == item_id,
                BalanceItemModel.user_id == user_id,
            )
            .first()
        )
        if not row:
            raise ValueError(f"balance_item {item_id} not found")
        return row

    def create(self, data: BalanceItemCreate, user_id: int) -> BalanceItemModel:
        row = BalanceItemModel(user_id=user_id, **data.model_dump())
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def update(
        self, item_id: int, data: BalanceItemUpdate, user_id: int
    ) -> BalanceItemModel:
        row = self.get_by_id(item_id, user_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        row.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(row)
        return row

    def delete(self, item_id: int, user_id: int) -> None:
        row = self.get_by_id(item_id, user_id)
        self._db.delete(row)
        self._db.commit()

    def delete_by_snapshot(self, snapshot_id: int, user_id: int) -> None:
        self._db.query(BalanceItemModel).filter(
            BalanceItemModel.snapshot_id == snapshot_id,
            BalanceItemModel.user_id == user_id,
        ).delete()
        self._db.commit()

    def copy_snapshot(
        self, from_snapshot_id: int, to_snapshot_id: int, user_id: int
    ) -> int:
        """Clone all items from from_snapshot_id into to_snapshot_id. Returns count."""
        source_items = (
            self._db.query(BalanceItemModel)
            .filter(
                BalanceItemModel.snapshot_id == from_snapshot_id,
                BalanceItemModel.user_id == user_id,
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for src in source_items:
            new_item = BalanceItemModel(
                snapshot_id=to_snapshot_id,
                user_id=user_id,
                account_id=src.account_id,
                sub_account_id=src.sub_account_id,
                category=src.category,
                side=src.side,
                name=src.name,
                amount=src.amount,
                currency=src.currency,
                note=src.note,
                price=src.price,
                quantity=src.quantity,
                start_date=src.start_date,
                end_date=src.end_date,
                interest_rate=src.interest_rate,
                monthly_payment=src.monthly_payment,
                create_time=now,
                update_time=now,
            )
            self._db.add(new_item)
        self._db.commit()
        return len(source_items)
