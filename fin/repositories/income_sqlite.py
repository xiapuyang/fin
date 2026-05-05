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

    def get_by_id(self, id: int) -> IncomeModel | None:
        return self._db.query(IncomeModel).filter(IncomeModel.id == id).first()

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

    def update(self, id: str, data: IncomeUpdate) -> IncomeModel:
        income = self.get_by_id(id)
        if income is None:
            raise ValueError(f"Income {id} not found")
        for field, val in data.model_dump(exclude_unset=True).items():
            setattr(income, field, val)
        income.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(income)
        return income

    def delete(self, id: str) -> None:
        income = self.get_by_id(id)
        if income:
            self._db.delete(income)
            self._db.commit()
