from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.holding import HoldingModel
from fin.schemas.holding import HoldingCreate, HoldingUpdate


class HoldingSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[HoldingModel]:
        return (
            self._db.query(HoldingModel)
            .filter(HoldingModel.user_id == user_id)
            .order_by(HoldingModel.code)
            .all()
        )

    def get_by_id(self, id: int, user_id: int) -> HoldingModel | None:
        return (
            self._db.query(HoldingModel)
            .filter(HoldingModel.id == id, HoldingModel.user_id == user_id)
            .first()
        )

    def create(self, data: HoldingCreate, user_id: int) -> HoldingModel:
        holding = HoldingModel(
            user_id=user_id,
            code=data.code,
            name=data.name,
            market=data.market,
            currency=data.currency,
            account=data.account,
            snapshot_name=data.snapshot_name,
            as_of_date=data.as_of_date,
            shares=data.shares,
            avg_cost=data.avg_cost,
            note=data.note,
        )
        self._db.add(holding)
        self._db.commit()
        self._db.refresh(holding)
        return holding

    def update(self, id: int, data: HoldingUpdate, user_id: int) -> HoldingModel:
        holding = self.get_by_id(id, user_id)
        if holding is None:
            raise ValueError(f"Holding {id} not found")
        for field, val in data.model_dump(exclude_unset=True).items():
            setattr(holding, field, val)
        holding.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(holding)
        return holding

    def delete(self, id: int, user_id: int) -> None:
        holding = self.get_by_id(id, user_id)
        if holding:
            self._db.delete(holding)
            self._db.commit()
