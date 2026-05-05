from sqlalchemy.orm import Session, selectinload

from fin.models.alert import AlertFireModel
from fin.repositories.base import AlertFireRepository


class AlertFireSQLiteRepository(AlertFireRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, alert_id: int, price: float, change_pct: float) -> AlertFireModel:
        fire = AlertFireModel(alert_id=alert_id, price=price, change_pct=change_pct)
        self._db.add(fire)
        self._db.commit()
        self._db.refresh(fire)
        return fire

    def get_by_alert(self, alert_id: int) -> list[AlertFireModel]:
        return (
            self._db.query(AlertFireModel)
            .filter(AlertFireModel.alert_id == alert_id)
            .order_by(AlertFireModel.fired_at.desc())
            .all()
        )

    def get_recent(self, limit: int = 50) -> list[AlertFireModel]:
        return (
            self._db.query(AlertFireModel)
            .options(selectinload(AlertFireModel.alert))
            .order_by(AlertFireModel.fired_at.desc())
            .limit(limit)
            .all()
        )
