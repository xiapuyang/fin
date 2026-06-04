from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from fin.database import Base


class BenchmarkCustomSchemeModel(Base):
    __tablename__ = "benchmark_custom_schemes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    allocations_json = Column(
        String, nullable=False
    )  # JSON: [{"symbol": str, "pct": float}]
    cash_pct = Column(Float, nullable=False, default=0.0)
    enabled = Column(Integer, nullable=False, default=1)
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
