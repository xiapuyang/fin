from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from fin.database import Base


class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    name = Column(String, nullable=False)
    condition = Column(
        String, nullable=False
    )  # price_gte, price_lte, change_gte, change_lte
    value = Column(Float, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    user_id = Column(BigInteger, nullable=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    fired_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    price = Column(Float, nullable=False)
    change_pct = Column(Float, nullable=False)

    alert = relationship("AlertModel", back_populates="fires")
