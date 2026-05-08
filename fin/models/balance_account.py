from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String

from fin.database import Base


class BalanceAccountModel(Base):
    __tablename__ = "balance_accounts"
    __table_args__ = (
        # COALESCE(parent_id, -1) makes top-level accounts (parent_id IS NULL) comparable
        # Enforced at DB level via: CREATE UNIQUE INDEX uq_balance_account ON balance_accounts (user_id, COALESCE(parent_id, -1), name)
        Index("uq_balance_account", "user_id", "parent_id", "name"),
    )

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
