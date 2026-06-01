from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from fin.database import Base


class DividendHistoryModel(Base):
    __tablename__ = "dividend_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, unique=True)
    ex_date = Column(String, nullable=True)  # next upcoming ex-dividend date
    pay_date = Column(String, nullable=True)  # next payment date
    annual_rate = Column(Float, nullable=True)  # per-share annual dividend
    history_json = Column(String, nullable=True)  # JSON: [{date, amount}]
    fetched_at = Column(String, nullable=True)  # ISO datetime of last yfinance fetch
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
