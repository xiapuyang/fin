from datetime import datetime

from sqlalchemy.orm import Session, selectinload

from fin.models.alert import AlertModel
from fin.models.user import MOCK_USER_ID
from fin.repositories.base import AlertRepository
from fin.schemas.alert import AlertCreate, AlertUpdate
from fin.services.quote import normalize_symbol


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

    def bulk_create(
        self, items: list[AlertCreate], user_id: int
    ) -> tuple[list[AlertModel], int]:
        """Insert many alerts; pre-filter duplicates by (symbol, condition, value).

        Symbols are normalized (e.g. `.SPX` → `^GSPC`) before the dedup key is
        computed, matching the single-create endpoint's behavior. Dedup runs
        against both existing DB rows and earlier rows in the same input batch.
        """
        existing = {
            (a.symbol, a.condition, a.value)
            for a in self._db.query(AlertModel)
            .filter(AlertModel.user_id == user_id)
            .all()
        }
        to_insert: list[AlertModel] = []
        skipped = 0
        for item in items:
            normalized = item.model_copy(
                update={"symbol": normalize_symbol(item.symbol)}
            )
            key = (normalized.symbol, normalized.condition, normalized.value)
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            to_insert.append(AlertModel(user_id=user_id, **normalized.model_dump()))
        if to_insert:
            self._db.add_all(to_insert)
            self._db.commit()
            for m in to_insert:
                self._db.refresh(m)
        return to_insert, skipped
