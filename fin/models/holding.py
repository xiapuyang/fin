from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)

from fin.database import Base


class HoldingModel(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "account", "code", "snapshot_name", name="uq_holding_snapshot"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    code = Column(String, nullable=False)
    name = Column(String, nullable=True)
    market = Column(String, nullable=False)
    currency = Column(String, nullable=False, default="USD")
    account = Column(
        String, nullable=True
    )  # investment account name (IBKR, 招商证券, …)
    snapshot_name = Column(
        String, nullable=True
    )  # snapshot group label (e.g. "2024-01-01")
    as_of_date = Column(
        String, nullable=True
    )  # baseline date; only txns after this stack on top
    shares = Column(Float, nullable=False, default=0.0)
    avg_cost = Column(Float, nullable=False, default=0.0)
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
