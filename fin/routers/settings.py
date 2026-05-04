import json

from fastapi import APIRouter
from pydantic import BaseModel

from fin import settings as settings_store
from fin.config import LAST_CHECK_PATH

router = APIRouter(prefix="/api")


class SettingsPayload(BaseModel):
    notify_email: str | None = None
    notify_enabled: bool | None = None


@router.get("/settings")
def get_settings():
    return settings_store.load()


@router.put("/settings")
def put_settings(data: SettingsPayload):
    return settings_store.save(data.model_dump(exclude_none=True))


@router.get("/last-check")
def get_last_check():
    if not LAST_CHECK_PATH.exists():
        return {"checked_at": None}
    return json.loads(LAST_CHECK_PATH.read_text())
