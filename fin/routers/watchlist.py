import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from fin.database import get_db
from fin.models.user import MOCK_USER_ID
from fin.models.watchlist import WatchlistModel
from fin.repositories.watchlist_sqlite import WatchlistSQLiteRepository
from fin.schemas.watchlist import WatchlistAdd, WatchlistItem
from fin.services.quote import normalize_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _to_item(w: WatchlistModel) -> WatchlistItem:
    """Convert a WatchlistModel ORM instance to a WatchlistItem schema.

    Args:
        w: ORM model instance.

    Returns:
        WatchlistItem populated from the model fields.
    """
    return WatchlistItem(
        symbol=w.symbol,
        name=w.name,
        market=w.market,
        currency=w.currency,
    )


@router.get("/watchlist", response_model=list[WatchlistItem])
def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItem]:
    """Return all watchlist entries ordered by creation time.

    Args:
        db: Injected SQLAlchemy session.

    Returns:
        List of WatchlistItem instances.
    """
    repo = WatchlistSQLiteRepository(db)
    return [_to_item(w) for w in repo.get_all(MOCK_USER_ID)]


@router.post("/watchlist", response_model=WatchlistItem, status_code=201)
def add_watchlist(data: WatchlistAdd, db: Session = Depends(get_db)) -> WatchlistItem:
    """Add a symbol to the watchlist (idempotent — ignores duplicates).

    Args:
        data: Validated request body with symbol and optional metadata.
        db: Injected SQLAlchemy session.

    Returns:
        The persisted WatchlistItem.

    Raises:
        HTTPException: 500 if the row cannot be retrieved after insert.
    """
    symbol = normalize_symbol(data.symbol.upper())
    repo = WatchlistSQLiteRepository(db)
    item = repo.add(symbol, data.name, data.market, data.currency, MOCK_USER_ID)
    if item is None:
        raise HTTPException(
            status_code=500, detail="Watchlist entry unavailable after insert"
        )
    logger.info("Watchlist add: %s", symbol)
    return _to_item(item)


@router.delete("/watchlist/{symbol:path}", status_code=204)
def remove_watchlist(symbol: str, db: Session = Depends(get_db)) -> Response:
    """Remove a symbol from the watchlist (no-op if absent).

    Args:
        symbol: URL-encoded stock symbol to remove.
        db: Injected SQLAlchemy session.

    Returns:
        204 No Content.
    """
    normalized = normalize_symbol(symbol.upper())
    repo = WatchlistSQLiteRepository(db)
    repo.remove(normalized, MOCK_USER_ID)
    return Response(status_code=204)
