from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from fin.models.watchlist import WatchlistModel
from fin.schemas.watchlist import WatchlistAdd
from fin.services.quote import normalize_symbol


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

    def bulk_create(self, items: list[WatchlistAdd], user_id: int) -> tuple[int, int]:
        """Insert many watchlist entries; pre-filter duplicates by symbol.

        Symbols are upper-cased and normalized via the same `normalize_symbol`
        helper used by the single-add endpoint, so bulk and single inserts
        share dedup semantics. Matches the `uq_watchlist_user_symbol`
        UniqueConstraint. Dedup runs against both existing DB rows and earlier
        rows in the same input batch. Uses `sqlite_insert` to match the
        single-add path (cheaper than ORM `add_all` for large batches and
        gives the DB a second-chance dedup if the in-Python set misses
        anything).

        Returns:
            Tuple of (created_count, skipped_count).
        """
        existing = {
            w.symbol
            for w in self._db.query(WatchlistModel)
            .filter(WatchlistModel.user_id == user_id)
            .all()
        }
        rows: list[dict] = []
        skipped = 0
        for item in items:
            symbol = normalize_symbol(item.symbol.upper())
            if symbol in existing:
                skipped += 1
                continue
            existing.add(symbol)
            rows.append(
                {
                    "user_id": user_id,
                    "symbol": symbol,
                    "name": item.name,
                    "market": item.market,
                    "currency": item.currency,
                }
            )
        if rows:
            stmt = (
                sqlite_insert(WatchlistModel)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["user_id", "symbol"])
            )
            self._db.execute(stmt)
            self._db.commit()
        return len(rows), skipped
