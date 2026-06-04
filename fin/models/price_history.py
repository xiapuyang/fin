from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String, UniqueConstraint
from sqlalchemy import Integer

from fin.database import Base


class PriceHistoryModel(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    close = Column(Float, nullable=False)
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_price_history_sym_date"),
    )
