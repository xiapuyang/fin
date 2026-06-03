from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from fin.schemas._validators import validate_nonempty


def _check_change_value(condition: Optional[str], value: Optional[float]) -> None:
    """Validate that change_lte value is negative and change_gte value is positive."""
    if condition == "change_lte" and value is not None and value >= 0:
        raise ValueError("跌幅超 (change_lte) 的 value 必须为负数")
    if condition == "change_gte" and value is not None and value <= 0:
        raise ValueError("涨幅超 (change_gte) 的 value 必须为正数")


class AlertCreate(BaseModel):
    symbol: str
    name: str
    condition: str
    value: float

    @field_validator("symbol", "name", "condition")
    @classmethod
    def fields_nonempty(cls, v: str) -> str:
        return validate_nonempty(v)

    @model_validator(mode="after")
    def check_condition_value(self) -> "AlertCreate":
        _check_change_value(self.condition, self.value)
        return self


class AlertUpdate(BaseModel):
    name: Optional[str] = None
    condition: Optional[str] = None
    value: Optional[float] = None
    enabled: Optional[bool] = None

    @model_validator(mode="after")
    def check_condition_value(self) -> "AlertUpdate":
        _check_change_value(self.condition, self.value)
        return self


class TriggeredInfo(BaseModel):
    at: str
    price: float


class AlertResponse(BaseModel):
    id: int
    code: str
    name: str
    cond: str
    threshold: float
    enabled: bool
    triggered: Optional[TriggeredInfo] = None
    created: str


class HistoryResponse(BaseModel):
    id: int
    time: str
    code: str
    name: str
    cond: str
    threshold: float
    actual: float
    change_pct: float
