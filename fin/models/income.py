from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String

from fin.database import Base


class IncomeModel(Base):
    __tablename__ = "income"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    date = Column(String, nullable=False)
    source = Column(String, nullable=False)
    category = Column(String, nullable=False)  # "dividend" | "interest" | "option"
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="USD")
    account = Column(String, nullable=True)
    code = Column(String, nullable=True)
    note = Column(String, nullable=True)
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
