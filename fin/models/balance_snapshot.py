from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint

from fin.database import Base


class BalanceSnapshotModel(Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "snapshot_date", "label", name="uq_balance_snapshot"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    snapshot_date = Column(String, nullable=False)  # YYYY-MM-DD
    label = Column(String, nullable=False)
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
