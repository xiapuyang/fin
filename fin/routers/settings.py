import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fin import settings as settings_store
from fin.config import LAST_CHECK_PATH, SUPPORTED_CURRENCIES
from fin.database import get_db
from fin.services.providers import build_default_providers
from fin.services.quote import QuoteService

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_FX_PAIRS = {"USD": "USDCNY=X", "HKD": "HKDCNY=X", "CAD": "CADCNY=X"}
_FX_FALLBACK = {"USD": 7.24, "HKD": 0.93, "CAD": 5.30, "CNY": 1.0}


class SettingsPayload(BaseModel):
    notify_email: str | None = None
    notify_enabled: bool | None = None
    timezone: str | None = None
    birth_date: str | None = None
    fire_monthly_exp: float | None = None
    fire_cagr: float | None = None
    fire_monthly: float | None = None
    fire_swr: float | None = None
    fire_manual_age: int | None = None
    fire_inflation: float | None = None
    fire_target_age: int | None = None
    fire_mc_sigma: int | None = None
    currency: str | None = None


@router.get("/config")
def get_config():
    """Return static app configuration consumed by the frontend."""
    return {"currencies": SUPPORTED_CURRENCIES}


@router.get("/settings")
def get_settings():
    return settings_store.load()


@router.put("/settings")
def put_settings(data: SettingsPayload):
    return settings_store.save(data.model_dump(exclude_none=True))


@router.get("/fx")
def get_fx(db: Session = Depends(get_db)):
    """Return CNY-based FX rates via QuoteService."""
    try:
        rates = QuoteService(db, build_default_providers()).get_fx(_FX_PAIRS)
        return {**_FX_FALLBACK, **rates}
    except Exception as exc:
        logger.warning("FX fetch failed: %s", exc)
        return _FX_FALLBACK


@router.get("/rebalance")
def get_rebalance():
    return settings_store.load().get("rebalance") or {}


@router.put("/rebalance")
def put_rebalance(data: Any = Body(...)):
    settings_store.save({"rebalance": data})
    return data


@router.get("/last-check")
def get_last_check():
    if not LAST_CHECK_PATH.exists():
        return {"checked_at": None}
    try:
        return json.loads(LAST_CHECK_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"checked_at": None}
