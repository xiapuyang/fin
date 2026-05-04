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

    def get_all(self) -> list[WatchlistModel]:
        """Return all watchlist entries ordered by creation time.

        Returns:
            List of WatchlistModel instances.
        """
        return self._db.query(WatchlistModel).order_by(WatchlistModel.create_time).all()

    def add(
        self, symbol: str, name: str | None, market: str | None, currency: str | None
    ) -> WatchlistModel | None:
        """Insert a watchlist entry, ignoring conflicts on symbol.

        Args:
            symbol: Normalized stock symbol (unique key).
            name: Human-readable name, may be None.
            market: Market identifier (US, HK, CN), may be None.
            currency: ISO currency code, may be None.

        Returns:
            The existing or newly inserted WatchlistModel, or None on concurrent deletion.
        """
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
        """Delete the watchlist entry for the given symbol (no-op if absent).

        Args:
            symbol: Normalized stock symbol to remove.
        """
        self._db.query(WatchlistModel).filter(WatchlistModel.symbol == symbol).delete()
        self._db.commit()
