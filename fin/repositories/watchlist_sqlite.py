from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from fin.models.watchlist import WatchlistModel


class WatchlistSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self) -> list[WatchlistModel]:
        return self._db.query(WatchlistModel).order_by(WatchlistModel.create_time).all()

    def add(
        self, symbol: str, name: str | None, market: str | None, currency: str | None
    ) -> WatchlistModel:
        stmt = (
            sqlite_insert(WatchlistModel)
            .values(symbol=symbol, name=name, market=market, currency=currency)
            .on_conflict_do_nothing(index_elements=["symbol"])
        )
        self._db.execute(stmt)
        self._db.commit()
        return (
            self._db.query(WatchlistModel)
            .filter(WatchlistModel.symbol == symbol)
            .first()
        )

    def remove(self, symbol: str) -> None:
        self._db.query(WatchlistModel).filter(WatchlistModel.symbol == symbol).delete()
        self._db.commit()
