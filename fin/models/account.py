from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint

from fin.database import Base


class AccountModel(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_account_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    name = Column(String, nullable=False)
    currency = Column(String, nullable=True, default="CNY")
    note = Column(String, nullable=True)
    cutoff_date = Column(String, nullable=True)
    balance_account_id = Column(Integer, nullable=True)
    balance_sub_account_id = Column(Integer, nullable=True)
    symbol_markets = Column(String, nullable=True)  # JSON: {"013308": "HK"}
    benchmark_enabled = Column(String, nullable=True, default="0")
    benchmark_schemes = Column(
        String, nullable=True
    )  # JSON: {enabled_defaults, custom_schemes}
    rebalance_enabled = Column(String, nullable=True, default="0")
    rebalance_config = Column(String, nullable=True)  # JSON: {type, ...}
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
