from typing import Optional

from pydantic import BaseModel


class AlertCreate(BaseModel):
    symbol: str
    name: str
    condition: str
    value: float


class AlertUpdate(BaseModel):
    name: Optional[str] = None
    condition: Optional[str] = None
    value: Optional[float] = None
    enabled: Optional[bool] = None


class TriggeredInfo(BaseModel):
    at: str
    price: float


class AlertResponse(BaseModel):
    id: str
    code: str
    name: str
    cond: str
    threshold: float
    enabled: bool
    triggered: Optional[TriggeredInfo] = None
    created: str


class HistoryResponse(BaseModel):
    id: str
    time: str
    code: str
    name: str
    cond: str
    threshold: float
    actual: float
    change_pct: float
