from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

from fin.schemas._validators import validate_date


class HoldingCreate(BaseModel):
    code: str
    name: Optional[str] = None
    market: Literal["US", "HK", "CN", "CA", "CRYPTO"]
    currency: str = "USD"
    account: Optional[str] = None
    snapshot_name: str
    shares: float
    avg_cost: float = 0.0
    note: Optional[str] = None

    @field_validator("snapshot_name")
    @classmethod
    def snapshot_name_is_date(cls, v: str) -> str:
        return validate_date(v)

    @model_validator(mode="after")
    def check_values(self) -> "HoldingCreate":
        if self.shares <= 0:
            raise ValueError("shares must be > 0")
        if self.avg_cost < 0:
            raise ValueError("avg_cost must be >= 0")
        return self


class HoldingUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    market: Optional[Literal["US", "HK", "CN", "CA", "CRYPTO"]] = None
    currency: Optional[str] = None
    account: Optional[str] = None
    snapshot_name: Optional[str] = None
    shares: Optional[float] = None
    avg_cost: Optional[float] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def check_non_negative(self) -> "HoldingUpdate":
        if self.shares is not None and self.shares < 0:
            raise ValueError("shares must be >= 0")
        if self.avg_cost is not None and self.avg_cost < 0:
            raise ValueError("avg_cost must be >= 0")
        return self


class HoldingResponse(BaseModel):
    id: int
    code: str
    name: Optional[str]
    market: str
    currency: str
    account: Optional[str]
    snapshot_name: Optional[str]
    shares: float
    avg_cost: float
    note: Optional[str]
    create_time: str
    update_time: str
