from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)

from fin.database import Base


class LedgerModel(Base):
    __tablename__ = "ledger"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "direction", "name", "date", "amount", name="uq_ledger_dedup"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    direction = Column(String, nullable=False)  # "income" | "expense"
    name = Column(String, nullable=False)
    date = Column(String, nullable=False)  # YYYY-MM-DD
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="CNY")
    category = Column(String, nullable=False)
    orig_category = Column(
        String, nullable=True
    )  # original import label (e.g. Notion 分类)
    subcategory = Column(String, nullable=True)  # user-defined grouping
    recurring_type = Column(
        String, nullable=True
    )  # monthly | annual | semi_annual | every_4months
    is_expired = Column(Boolean, nullable=False, default=False)
    expiry_date = Column(String, nullable=True)
    note = Column(String, nullable=True)
    amounts_json = Column(
        String, nullable=True
    )  # JSON: {CNY, USD, CAD, HKD} at entry time
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
