from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String

from fin.database import Base


class TransactionModel(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    date = Column(String, nullable=False)
    code = Column(String, nullable=False)
    name = Column(String, nullable=True)
    side = Column(String, nullable=False)  # "buy" | "sell"
    shares = Column(Float, nullable=False, default=0.0)
    price = Column(Float, nullable=False, default=0.0)
    currency = Column(String, nullable=False, default="USD")
    account = Column(String, nullable=True)
    realized = Column(Float, nullable=True)
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
