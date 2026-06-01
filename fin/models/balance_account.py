from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from fin.database import Base


class BalanceAccountModel(Base):
    __tablename__ = "balance_accounts"
    # uq_balance_account COALESCE unique index is created in database._migrate_balance_indexes()

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, nullable=True)
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
