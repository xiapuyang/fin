from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from fin.database import Base


class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    symbol = Column(String, nullable=False)
    name = Column(String, nullable=False)
    condition = Column(
        String, nullable=False
    )  # price_gte, price_lte, change_gte, change_lte
    value = Column(Float, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    fires = relationship(
        "AlertFireModel",
        back_populates="alert",
        order_by="AlertFireModel.fired_at",
        cascade="all, delete-orphan",
    )


class AlertFireModel(Base):
    __tablename__ = "alert_fires"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    alert_id = Column(
        String, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    fired_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    price = Column(Float, nullable=False)
    change_pct = Column(Float, nullable=False)

    alert = relationship("AlertModel", back_populates="fires")
