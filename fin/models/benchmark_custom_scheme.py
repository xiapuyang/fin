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


class BenchmarkCustomSchemeModel(Base):
    __tablename__ = "benchmark_custom_schemes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    account_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    allocations_json = Column(
        String, nullable=False
    )  # JSON: [{"symbol": str, "pct": float}]
    cash_pct = Column(Float, nullable=False, default=0.0)
    enabled = Column(Integer, nullable=False, default=1)
    is_portfolio_snapshot = Column(Integer, nullable=False, default=0)
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "account_id", "name", name="uq_benchmark_custom_schemes_acct_name"
        ),
    )
