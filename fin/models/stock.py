from datetime import datetime

from sqlalchemy import Column, DateTime, Float, String

from fin.database import Base


class StockModel(Base):
    __tablename__ = "stocks"

    symbol = Column(String, primary_key=True)
    name = Column(String)
    currency = Column(String)
    price = Column(Float)
    prev_close = Column(Float)
    regular_close = Column(Float)
    open_price = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    turnover_rate = Column(Float)
    pe_ttm = Column(Float)
    pe_dynamic = Column(Float)
    pb = Column(Float)
    market_cap = Column(Float)
    total_shares = Column(Float)
    float_shares = Column(Float)
    float_market_cap = Column(Float)
    week_52_high = Column(Float)
    week_52_low = Column(Float)
    beta = Column(Float)
    dividend_ttm = Column(Float)
    dividend_rate = Column(Float)
    asset_type = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
