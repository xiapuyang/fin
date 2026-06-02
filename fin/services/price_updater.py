import logging
import threading
import time

from sqlalchemy.orm import Session

from fin.config import SYMBOLS_PATH
from fin.services.providers import build_default_providers
from fin.services.quote import QuoteService, normalize_symbol

logger = logging.getLogger(__name__)

UPDATE_INTERVAL = 300  # 5 minutes
BATCH_SIZE = 20
BATCH_PAUSE = 0.5  # seconds between batches


def _alert_symbols() -> set[str]:
    from fin.database import SessionLocal
    from fin.repositories.alert_sqlite import AlertSQLiteRepository

    db = SessionLocal()
    try:
        return {a.symbol for a in AlertSQLiteRepository(db).get_enabled()}
    finally:
        db.close()


def _portfolio_symbols() -> set[str]:
    """Collect unique symbols from holdings, transactions, and income tables."""
    from fin.database import SessionLocal
    from fin.models.holding import HoldingModel
    from fin.models.transaction import TransactionModel
    from fin.models.income import IncomeModel

    db = SessionLocal()
    try:
        h = {row[0] for row in db.query(HoldingModel.code).distinct().all() if row[0]}
        t = {
            row[0] for row in db.query(TransactionModel.code).distinct().all() if row[0]
        }
        i = {row[0] for row in db.query(IncomeModel.code).distinct().all() if row[0]}
        return h | t | i
    finally:
        db.close()


def collect_symbols() -> set[str]:
    symbols: set[str] = set()
    if SYMBOLS_PATH.exists():
        import json

        groups = json.loads(SYMBOLS_PATH.read_text(encoding="utf-8"))
        for group in groups.values():
            for entry in group:
                symbols.add(normalize_symbol(entry["code"]))
    symbols |= _alert_symbols()
    symbols |= _portfolio_symbols()
    return symbols


def run_update_cycle(db: Session) -> None:
    providers = build_default_providers()
    service = QuoteService(db, providers)
    all_symbols = sorted(collect_symbols())
    logger.info("Price update: %d symbols", len(all_symbols))
    for i in range(0, len(all_symbols), BATCH_SIZE):
        batch = all_symbols[i : i + BATCH_SIZE]
        for symbol in batch:
            try:
                data = service.get_full_quote(symbol)
                if data:
                    service.upsert_quote(symbol, data)
                    logger.debug("Updated %s", symbol)
            except Exception:
                logger.exception("Failed to update %s", symbol)
        if i + BATCH_SIZE < len(all_symbols):
            time.sleep(BATCH_PAUSE)


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
