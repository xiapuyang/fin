import logging
import threading
import time

from sqlalchemy.orm import Session

from fin.config import SYMBOLS_PATH
from fin.repositories.stock_sqlite import StockSQLiteRepository
from fin.services.quote import fetch_full_quote, normalize_symbol

logger = logging.getLogger(__name__)

UPDATE_INTERVAL = 300  # 5 minutes


def _alert_symbols() -> set[str]:
    from fin.database import SessionLocal
    from fin.repositories.alert_sqlite import AlertSQLiteRepository

    db = SessionLocal()
    try:
        return {a.symbol for a in AlertSQLiteRepository(db).get_enabled()}
    finally:
        db.close()


def collect_symbols() -> set[str]:
    symbols: set[str] = set()
    if SYMBOLS_PATH.exists():
        import json

        groups = json.loads(SYMBOLS_PATH.read_text())
        for group in groups.values():
            for entry in group:
                symbols.add(normalize_symbol(entry["code"]))
    symbols |= _alert_symbols()
    return symbols


def run_update_cycle(db: Session) -> None:
    repo = StockSQLiteRepository(db)
    for symbol in collect_symbols():
        try:
            data = fetch_full_quote(symbol)
            if data:
                repo.upsert(symbol, data)
                logger.debug("Updated %s", symbol)
        except Exception:
            logger.exception("Failed to update %s", symbol)


def _loop() -> None:
    while True:
        try:
            from fin.database import SessionLocal

            db = SessionLocal()
            try:
                run_update_cycle(db)
            finally:
                db.close()
        except Exception:
            logger.exception("Price updater cycle failed")
        time.sleep(UPDATE_INTERVAL)


def start_price_updater() -> threading.Thread:
    t = threading.Thread(target=_loop, daemon=True, name="price-updater")
    t.start()
    logger.info("Price updater started (interval=%ds)", UPDATE_INTERVAL)
    return t
