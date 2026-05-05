from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from fin.database import Base


class AccountModel(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    name = Column(String, nullable=False)
    currency = Column(String, nullable=True, default="CNY")
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
