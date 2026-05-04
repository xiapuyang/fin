import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from fin.database import get_db
from fin.repositories.watchlist_sqlite import WatchlistSQLiteRepository
from fin.schemas.watchlist import WatchlistAdd, WatchlistItem
from fin.services.quote import normalize_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _to_item(w) -> dict:
    return {
        "symbol": w.symbol,
        "name": w.name,
        "market": w.market,
        "currency": w.currency,
    }


@router.get("/watchlist", response_model=list[WatchlistItem])
def list_watchlist(db: Session = Depends(get_db)):
    repo = WatchlistSQLiteRepository(db)
    return [_to_item(w) for w in repo.get_all()]


@router.post("/watchlist", response_model=WatchlistItem, status_code=201)
def add_watchlist(data: WatchlistAdd, db: Session = Depends(get_db)):
    symbol = normalize_symbol(data.symbol.upper())
    repo = WatchlistSQLiteRepository(db)
    item = repo.add(symbol, data.name, data.market, data.currency)
    logger.info("Watchlist add: %s", symbol)
    return _to_item(item)


@router.delete("/watchlist/{symbol:path}", status_code=204)
def remove_watchlist(symbol: str, db: Session = Depends(get_db)):
    normalized = normalize_symbol(symbol.upper())
    repo = WatchlistSQLiteRepository(db)
    repo.remove(normalized)
    return Response(status_code=204)
