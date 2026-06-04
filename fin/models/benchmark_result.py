from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from fin.database import Base


class BenchmarkResultModel(Base):
    __tablename__ = "benchmark_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False)
    computed_date = Column(String, nullable=False)  # "YYYY-MM-DD"
    portfolio_xirr = Column(Float, nullable=True)
    results_json = Column(String, nullable=True)  # JSON: [{id, name, xirr}]
    excluded_deposits = Column(Integer, nullable=True, default=0)
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
            "account_id", "computed_date", name="uq_benchmark_results_acct_date"
        ),
    )
