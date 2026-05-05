import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from fin import settings as settings_store
from fin.config import LAST_CHECK_PATH

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class SettingsPayload(BaseModel):
    notify_email: str | None = None
    notify_enabled: bool | None = None
    timezone: str | None = None


@router.get("/settings")
def get_settings():
    return settings_store.load()


@router.put("/settings")
def put_settings(data: SettingsPayload):
    return settings_store.save(data.model_dump(exclude_none=True))


@router.get("/fx")
def get_fx():
    """Return CNY-based FX rates fetched live from yfinance."""
    try:
        import yfinance as yf

        pairs = {"USD": "USDCNY=X", "HKD": "HKDCNY=X", "EUR": "EURCNY=X"}
        rates = {"USD": 7.24, "HKD": 0.93, "EUR": 7.84, "CNY": 1.0}
        for ccy, ticker in pairs.items():
            try:
                info = yf.Ticker(ticker).fast_info
                price = getattr(info, "last_price", None) or getattr(
                    info, "regularMarketPrice", None
                )
                if price and price > 0:
                    rates[ccy] = round(float(price), 4)
            except Exception:
                pass
        return rates
    except Exception as exc:
        logger.warning("FX fetch failed: %s", exc)
        return {"USD": 7.24, "HKD": 0.93, "EUR": 7.84, "CNY": 1.0}


@router.get("/last-check")
def get_last_check():
    if not LAST_CHECK_PATH.exists():
        return {"checked_at": None}
    try:
        return json.loads(LAST_CHECK_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"checked_at": None}
