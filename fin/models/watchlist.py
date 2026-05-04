from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from fin.database import Base


class WatchlistModel(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    market = Column(String)
    currency = Column(String)
    create_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    update_time = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
