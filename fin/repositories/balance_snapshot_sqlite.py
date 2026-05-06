from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.balance_snapshot import BalanceSnapshotModel
from fin.schemas.balance_snapshot import BalanceSnapshotCreate, BalanceSnapshotUpdate


class BalanceSnapshotSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[tuple[BalanceSnapshotModel, int]]:
        """Return (snapshot, item_count) pairs ordered by snapshot_date asc."""
        from fin.models.balance_item import BalanceItemModel
        from sqlalchemy import func

        rows = (
            self._db.query(
                BalanceSnapshotModel,
                func.count(BalanceItemModel.id).label("item_count"),
            )
            .outerjoin(
                BalanceItemModel,
                (BalanceItemModel.snapshot_id == BalanceSnapshotModel.id)
                & (BalanceItemModel.user_id == user_id),
            )
            .filter(BalanceSnapshotModel.user_id == user_id)
            .group_by(BalanceSnapshotModel.id)
            .order_by(BalanceSnapshotModel.snapshot_date)
            .all()
        )
        return rows

    def get_by_id(self, snapshot_id: int, user_id: int) -> BalanceSnapshotModel:
        row = (
            self._db.query(BalanceSnapshotModel)
            .filter(
                BalanceSnapshotModel.id == snapshot_id,
                BalanceSnapshotModel.user_id == user_id,
            )
            .first()
        )
        if not row:
            raise ValueError(f"balance_snapshot {snapshot_id} not found")
        return row

    def create(self, data: BalanceSnapshotCreate, user_id: int) -> BalanceSnapshotModel:
        row = BalanceSnapshotModel(user_id=user_id, **data.model_dump())
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def update(
        self, snapshot_id: int, data: BalanceSnapshotUpdate, user_id: int
    ) -> BalanceSnapshotModel:
        row = self.get_by_id(snapshot_id, user_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        row.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(row)
        return row

    def delete(self, snapshot_id: int, user_id: int) -> None:
        """Delete snapshot; cascades item deletion via BalanceItemSQLiteRepository."""
        from fin.repositories.balance_item_sqlite import BalanceItemSQLiteRepository

        BalanceItemSQLiteRepository(self._db).delete_by_snapshot(snapshot_id, user_id)
        row = self.get_by_id(snapshot_id, user_id)
        self._db.delete(row)
        self._db.commit()
