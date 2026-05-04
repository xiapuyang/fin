from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from fin.database import Base


class WatchlistModel(Base):
    """SQLAlchemy ORM model for the user's watchlist."""

    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, unique=True, nullable=False, index=True)
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
