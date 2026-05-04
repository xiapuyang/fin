from pydantic import BaseModel, Field


class WatchlistAdd(BaseModel):
    """Request schema for adding a symbol to the watchlist."""

    symbol: str = Field(..., min_length=1, max_length=32)
    name: str | None = None
    market: str | None = None
    currency: str | None = None


class WatchlistItem(BaseModel):
    """Response schema for a single watchlist entry."""

    symbol: str
    name: str | None = None
    market: str | None = None
    currency: str | None = None
