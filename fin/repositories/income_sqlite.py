from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.income import IncomeModel
from fin.schemas.income import IncomeCreate, IncomeUpdate


class IncomeSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[IncomeModel]:
        return (
            self._db.query(IncomeModel)
            .filter(IncomeModel.user_id == user_id)
            .order_by(IncomeModel.date.desc())
            .all()
        )

    def get_by_id(self, id: int, user_id: int) -> IncomeModel | None:
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
        income = self._build_model(data, user_id)
        self._db.add(income)
        self._db.commit()
        self._db.refresh(income)
        return income

    def update(self, id: int, data: IncomeUpdate, user_id: int) -> IncomeModel:
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

        inserted: list[IncomeModel] = []
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
                    create_time=datetime.now(timezone.utc),
                    update_time=datetime.now(timezone.utc),
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "date", "source", "amount", "currency"]
                )
            )
            result = self._db.execute(stmt)
            if result.rowcount:
                inserted.append(
                    self._db.query(IncomeModel)
                    .filter(IncomeModel.id == result.inserted_primary_key[0])
                    .first()
                )
        self._db.commit()
        return [m for m in inserted if m is not None]

    def delete(self, id: int, user_id: int) -> None:
        income = self.get_by_id(id, user_id)
        if income:
            self._db.delete(income)
            self._db.commit()
