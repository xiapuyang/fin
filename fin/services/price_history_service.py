import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from fin.models.price_history import PriceHistoryModel
from fin.services.quote import normalize_symbol

logger = logging.getLogger(__name__)

_STALE_DAYS = 1  # re-fetch if most recent row is older than yesterday


def fetch_symbol(db: Session, symbol: str, since_date: str) -> list[dict]:
    """Return historical closes for *symbol* starting from *since_date* ("YYYY-MM-DD").

    Incremental: only fetches via the provider when the cache is stale (no row for
    yesterday or today UTC). Stores rows keyed by the original *symbol* string;
    normalization is applied only for provider routing.

    Args:
        db: SQLAlchemy session.
        symbol: Original ticker string (e.g. "SPY", "000300.SS", "013308").
        since_date: Earliest date to include in the returned list.

    Returns:
        List of {"date": "YYYY-MM-DD", "close": float} sorted ascending by date,
        filtered to dates >= since_date.
    """
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=_STALE_DAYS)

    row = db.execute(
        text("SELECT MAX(date) FROM price_history WHERE symbol = :sym"),
        {"sym": symbol},
    ).scalar()

    if row is None or row < str(yesterday):
        _fetch_from_provider(db, symbol, row, since_date, today)

    rows = db.execute(
        text(
            "SELECT date, close FROM price_history "
            "WHERE symbol = :sym AND date >= :since ORDER BY date ASC"
        ),
        {"sym": symbol, "since": since_date},
    ).fetchall()
    return [{"date": r[0], "close": r[1]} for r in rows]


def _fetch_from_provider(
    db: Session,
    symbol: str,
    max_date: str | None,
    since_date: str,
    today: date,
) -> None:
    """Fetch history via the appropriate provider and upsert into price_history.

    Routes through the provider abstraction so OTC funds (e.g. 013308) go to
    ChinaFundProvider/akshare and exchange-listed symbols go to YFinanceProvider.

    Args:
        db: SQLAlchemy session.
        symbol: Original symbol to store rows under.
        max_date: Most recent date already in DB, or None if table is empty for symbol.
        since_date: Fallback start date when no cached rows exist.
        today: Today's UTC date.
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from fin.services.providers import build_default_providers

    if max_date:
        start = str(
            (datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)).date()
        )
    else:
        start = since_date

    end = str(today + timedelta(days=1))

    yf_symbol = normalize_symbol(symbol)
    providers = build_default_providers()
    provider = next((p for p in providers if p.supports(yf_symbol)), None)
    if provider is None:
        logger.warning("no provider supports symbol: %s", symbol)
        return

    raw_rows = provider.fetch_history(yf_symbol, start, end)
    if not raw_rows:
        logger.debug("provider returned empty history for %s start=%s", symbol, start)
        return

    rows = [
        {"symbol": symbol, "date": r["date"], "close": r["close"]} for r in raw_rows
    ]
    stmt = sqlite_insert(PriceHistoryModel).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "date"],
        set_={"close": stmt.excluded.close},
    )
    db.execute(stmt)
    db.commit()
    logger.debug("Upserted %d price rows for %s", len(rows), symbol)
