from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.income import IncomeModel
from fin.schemas.income import IncomeCreate, IncomeUpdate


class IncomeSQLiteRepository:
    """SQLite-backed repository for income records (dividends, interest, deposits, etc.)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[IncomeModel]:
        """Return all income records for a user, most recent first."""
        return (
            self._db.query(IncomeModel)
            .filter(IncomeModel.user_id == user_id)
            .order_by(IncomeModel.date.desc())
            .all()
        )

    def get_by_id(self, id: int, user_id: int) -> IncomeModel | None:
        """Return a single income record by primary key, or None if not found."""
        return (
            self._db.query(IncomeModel)
            .filter(IncomeModel.id == id, IncomeModel.user_id == user_id)
            .first()
        )

    def _build_model(self, data: IncomeCreate, user_id: int) -> IncomeModel:
        return IncomeModel(
            user_id=user_id,
            date=data.date,
            source=data.source,
            category=data.category,
            amount=data.amount,
            currency=data.currency,
            account=data.account,
            code=data.code,
            note=data.note,
        )

    def create(self, data: IncomeCreate, user_id: int) -> IncomeModel:
        """Insert a new income record and return the persisted model."""
        income = self._build_model(data, user_id)
        self._db.add(income)
        self._db.commit()
        self._db.refresh(income)
        return income

    def update(self, id: int, data: IncomeUpdate, user_id: int) -> IncomeModel:
        """Apply a partial update to an income record.

        Raises:
            ValueError: If the income record does not exist.
        """
        income = self.get_by_id(id, user_id)
        if income is None:
            raise ValueError(f"Income {id} not found")
        for field, val in data.model_dump(exclude_unset=True).items():
            setattr(income, field, val)
        income.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(income)
        return income

    def bulk_create(self, items: list[IncomeCreate], user_id: int) -> list[IncomeModel]:
        """Bulk-insert income records, skipping exact duplicates (same date/source/amount/currency).

        Args:
            items: List of income records to insert.
            user_id: Owner user ID for all records.

        Returns:
            Only the newly inserted models (duplicates are silently skipped).
        """
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        now = datetime.now(timezone.utc)
        inserted_ids: list[int] = []
        for d in items:
            stmt = (
                sqlite_insert(IncomeModel)
                .values(
                    user_id=user_id,
                    date=d.date,
                    source=d.source,
                    category=d.category,
                    amount=d.amount,
                    currency=d.currency,
                    account=d.account,
                    code=d.code,
                    note=d.note,
                    create_time=now,
                    update_time=now,
                )
                .on_conflict_do_nothing()
            )
            result = self._db.execute(stmt)
            if result.rowcount:
                inserted_ids.append(result.inserted_primary_key[0])
        self._db.commit()
        if not inserted_ids:
            return []
        return (
            self._db.query(IncomeModel).filter(IncomeModel.id.in_(inserted_ids)).all()
        )

    def delete(self, id: int, user_id: int) -> None:
        """Delete an income record by primary key. No-op if not found."""
        income = self.get_by_id(id, user_id)
        if income:
            self._db.delete(income)
            self._db.commit()
