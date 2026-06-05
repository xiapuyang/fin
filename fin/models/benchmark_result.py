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


class BenchmarkResultModel(Base):
    __tablename__ = "benchmark_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    account_id = Column(Integer, nullable=False)
    bench_id = Column(String, nullable=False)  # "__portfolio__" or scheme ID
    computed_date = Column(String, nullable=False)  # "YYYY-MM-DD"
    xirr = Column(Float, nullable=True)
    current_value_usd = Column(Float, nullable=True)  # terminal value in USD
    computed_at = Column(DateTime, nullable=True)  # exact timestamp of last compute
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
            "account_id",
            "bench_id",
            "computed_date",
            name="uq_benchmark_results_acct_bench_date",
        ),
    )
