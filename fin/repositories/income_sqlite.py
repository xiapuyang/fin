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

    def create(self, data: IncomeCreate, user_id: int) -> IncomeModel:
        income = IncomeModel(
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
        models = [
            IncomeModel(
                user_id=user_id,
                date=d.date,
                source=d.source,
                category=d.category,
                amount=d.amount,
                currency=d.currency,
                account=d.account,
                code=d.code,
                note=d.note,
            )
            for d in items
        ]
        self._db.add_all(models)
        self._db.commit()
        for m in models:
            self._db.refresh(m)
        return models

    def delete(self, id: int, user_id: int) -> None:
        income = self.get_by_id(id, user_id)
        if income:
            self._db.delete(income)
            self._db.commit()
