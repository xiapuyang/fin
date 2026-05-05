from datetime import datetime

from sqlalchemy.orm import Session, selectinload

from fin.models.alert import AlertModel
from fin.models.user import MOCK_USER_ID
from fin.repositories.base import AlertRepository
from fin.schemas.alert import AlertCreate, AlertUpdate


class AlertSQLiteRepository(AlertRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def _load(self):
        return selectinload(AlertModel.fires)

    def get_all(self) -> list[AlertModel]:
        return (
            self._db.query(AlertModel)
            .options(self._load())
            .order_by(AlertModel.created_at.desc())
            .all()
        )

    def get_enabled(self) -> list[AlertModel]:
        return (
            self._db.query(AlertModel)
            .options(self._load())
            .filter(AlertModel.enabled == True)  # noqa: E712
            .all()
        )

    def get_by_id(self, id: int) -> AlertModel | None:
        return (
            self._db.query(AlertModel)
            .options(self._load())
            .filter(AlertModel.id == id)
            .first()
        )

    def create(self, data: AlertCreate) -> AlertModel:
        alert = AlertModel(
            symbol=data.symbol,
            name=data.name,
            condition=data.condition,
            value=data.value,
            user_id=MOCK_USER_ID,
        )
        self._db.add(alert)
        self._db.commit()
        self._db.refresh(alert)
        return alert

    def update(self, id: int, data: AlertUpdate) -> AlertModel:
        alert = self.get_by_id(id)
        if alert is None:
            raise ValueError(f"Alert {id} not found")
        for field, val in data.model_dump(exclude_unset=True).items():
            setattr(alert, field, val)
        alert.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(alert)
        return alert

    def delete(self, id: int) -> None:
        alert = self.get_by_id(id)
        if alert:
            self._db.delete(alert)
            self._db.commit()

    def disable(self, id: int) -> AlertModel:
        alert = self.get_by_id(id)
        if alert is None:
            raise ValueError(f"Alert {id} not found")
        alert.enabled = False
        alert.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(alert)
        return alert

    def reset(self, id: int) -> AlertModel:
        alert = self.get_by_id(id)
        if alert is None:
            raise ValueError(f"Alert {id} not found")
        alert.enabled = True
        alert.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(alert)
        return alert
