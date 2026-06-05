import json
import logging
import os
from typing import Any, Literal

from dotenv import set_key
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from fin import settings as settings_store
from fin.config import APP_CONFIG_PATH, DATA_DIR, LAST_CHECK_PATH, SUPPORTED_CURRENCIES
from fin.database import get_db
from fin.services.providers import build_default_providers
from fin.services.quote import QuoteService

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_FX_PAIRS = {"USD": "USDCNY=X", "HKD": "HKDCNY=X", "CAD": "CADCNY=X"}
_FX_FALLBACK = {"USD": 7.24, "HKD": 0.93, "CAD": 5.30, "CNY": 1.0}

_VALID_MARKETS = {"us", "hk", "cn", "ca"}


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
    language: Literal["en", "zh"] | None = None
    enabled_markets: list[str] | None = None

    @field_validator("enabled_markets")
    @classmethod
    def _validate_markets(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        unknown = [m for m in v if m not in _VALID_MARKETS]
        if unknown:
            raise ValueError(
                f"unknown markets: {unknown}; valid: {sorted(_VALID_MARKETS)}"
            )
        return v


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


@router.get("/rebalance/defaults")
def get_rebalance_defaults():
    """Return the list of system default rebalance presets from config/app.json."""
    try:
        cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("rebalance_defaults", [])
    except Exception as exc:
        logger.warning("Failed to load rebalance_defaults: %s", exc)
        return []


@router.get("/rebalance")
def get_rebalance():
    """Return the stored rebalance configuration.

    Reads rebalance_v3 first (v3 format); falls back to rebalance (v1/v2 legacy)
    so the frontend migration can detect the old format and write v3.
    """
    s = settings_store.load()
    return s.get("rebalance_v3") or s.get("rebalance") or {}


@router.put("/rebalance")
def put_rebalance(data: Any = Body(...)):
    """Persist rebalance configuration to rebalance_v3; legacy rebalance key is untouched."""
    settings_store.save({"rebalance_v3": data})
    return data


@router.get("/last-check")
def get_last_check():
    if not LAST_CHECK_PATH.exists():
        return {"checked_at": None}
    try:
        return json.loads(LAST_CHECK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"checked_at": None}


class CredentialsPayload(BaseModel):
    agentmail_api_key: str | None = None
    agentmail_inbox: str | None = None


@router.get("/settings/credentials")
def get_credentials():
    """Return credential metadata only — never the full API key.

    The API key is sensitive (it can charge the AgentMail account and
    read mailbox state). Returning it on GET makes it exfiltratable via
    DNS rebinding + permissive CORS. We surface only enough for the UI
    to confirm "a key is set" and show the last 4 characters as a
    visual hint.
    """
    api_key = os.environ.get("AGENTMAIL_API_KEY", "")
    return {
        "agentmail_api_key_set": bool(api_key),
        "agentmail_api_key_hint": api_key[-4:] if len(api_key) >= 8 else "",
        "agentmail_inbox": os.environ.get("FIN_AGENTMAIL_INBOX", ""),
    }


@router.put("/settings/credentials")
def put_credentials(data: CredentialsPayload):
    """Write AgentMail credentials to DATA_DIR/.env and update os.environ in place."""
    env_path = DATA_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.touch(exist_ok=True)
    if data.agentmail_api_key is not None:
        set_key(str(env_path), "AGENTMAIL_API_KEY", data.agentmail_api_key)
        os.environ["AGENTMAIL_API_KEY"] = data.agentmail_api_key
    if data.agentmail_inbox is not None:
        set_key(str(env_path), "FIN_AGENTMAIL_INBOX", data.agentmail_inbox)
        os.environ["FIN_AGENTMAIL_INBOX"] = data.agentmail_inbox
    return {"saved": True, "restart_required": False}
