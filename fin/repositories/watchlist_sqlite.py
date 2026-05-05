from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from fin.models.watchlist import WatchlistModel


class WatchlistSQLiteRepository:
    """SQLite-backed repository for watchlist entries."""

    def __init__(self, db: Session) -> None:
        """Initialize with an active SQLAlchemy session.

        Args:
            db: Active SQLAlchemy session.
        """
        self._db = db

    def get_all(self, user_id: int) -> list[WatchlistModel]:
        return (
            self._db.query(WatchlistModel)
            .filter(WatchlistModel.user_id == user_id)
            .order_by(WatchlistModel.create_time)
            .all()
        )

    def add(
        self,
        symbol: str,
        name: str | None,
        market: str | None,
        currency: str | None,
        user_id: int = 1,
    ) -> WatchlistModel | None:
        stmt = (
            sqlite_insert(WatchlistModel)
            .values(
                user_id=user_id,
                symbol=symbol,
                name=name,
                market=market,
                currency=currency,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "symbol"])
        )
        self._db.execute(stmt)
        self._db.commit()
        return (
            self._db.query(WatchlistModel)
            .filter(WatchlistModel.user_id == user_id, WatchlistModel.symbol == symbol)
            .first()
        )

    def remove(self, symbol: str, user_id: int = 1) -> None:
        self._db.query(WatchlistModel).filter(
            WatchlistModel.user_id == user_id, WatchlistModel.symbol == symbol
        ).delete()
        self._db.commit()
