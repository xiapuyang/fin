from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint

from fin.database import Base


class WatchlistModel(Base):
    """SQLAlchemy ORM model for the user's watchlist."""

    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_watchlist_user_symbol"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    symbol = Column(String, nullable=False, index=True)
    name = Column(String)
    market = Column(String)
    currency = Column(String)
    create_time = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
