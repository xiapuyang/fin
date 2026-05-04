from pydantic import BaseModel


class WatchlistAdd(BaseModel):
    symbol: str
    name: str | None = None
    market: str | None = None
    currency: str | None = None


class WatchlistItem(BaseModel):
    symbol: str
    name: str | None
    market: str | None
    currency: str | None
