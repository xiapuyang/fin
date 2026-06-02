import json
import logging
import os
from typing import Any

from dotenv import set_key
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fin import settings as settings_store
from fin.config import DATA_DIR, LAST_CHECK_PATH, SUPPORTED_CURRENCIES
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
    display_name: str | None = None
    birth_date: str | None = None
    fire_monthly_exp: float | None = None
    fire_cagr: float | None = None
    fire_monthly: float | None = None
    fire_swr: float | None = None
    fire_manual_age: int | None = None
    fire_inflation: float | None = None
    fire_target_age: int | None = None
    fire_mc_sigma: int | None = None
    fire_life_expectancy: int | None = None
    currency: str | None = None
    privacy_mask: bool | None = None


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
    """Return the stored rebalance configuration."""
    return settings_store.load().get("rebalance") or {}


@router.put("/rebalance")
def put_rebalance(data: Any = Body(...)):
    """Persist rebalance configuration and return it."""
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


class CredentialsPayload(BaseModel):
    agentmail_api_key: str | None = None
    agentmail_inbox: str | None = None


@router.get("/settings/credentials")
def get_credentials():
    """Return stored AgentMail credentials (localhost-only; values are not secrets on this machine)."""
    return {
        "agentmail_api_key": os.environ.get("AGENTMAIL_API_KEY", ""),
        "agentmail_inbox": os.environ.get("FIN_AGENTMAIL_INBOX", ""),
    }


@router.put("/settings/credentials")
def put_credentials(data: CredentialsPayload):
    """Write AgentMail credentials to DATA_DIR/.env without touching other keys."""
    env_path = DATA_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.touch(exist_ok=True)
    if data.agentmail_api_key is not None:
        set_key(str(env_path), "AGENTMAIL_API_KEY", data.agentmail_api_key)
    if data.agentmail_inbox is not None:
        set_key(str(env_path), "FIN_AGENTMAIL_INBOX", data.agentmail_inbox)
    return {"saved": True, "restart_required": True}
