from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String

from fin.database import Base


class BalanceItemModel(Base):
    __tablename__ = "balance_items"
    # uq_balance_item COALESCE unique index is created in database._migrate_balance_indexes()

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, nullable=False)
    user_id = Column(BigInteger, nullable=True)
    account_id = Column(Integer, nullable=True)
    sub_account_id = Column(Integer, nullable=True)
    category = Column(String, nullable=False)
    side = Column(String, nullable=False)  # "asset" | "liability"
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="CNY")
    note = Column(String, nullable=True)
    # display-only extra fields — do not affect totals
    price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    interest_rate = Column(Float, nullable=True)
    monthly_payment = Column(Float, nullable=True)
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
