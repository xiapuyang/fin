from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

from fin.schemas._validators import (
    validate_date,
    validate_nonempty,
    validate_optional_date,
)


class IncomeCreate(BaseModel):
    date: str
    source: str
    category: Literal["dividend", "interest", "option", "deposit", "withdrawal"]
    amount: float
    currency: str = "USD"
    account: Optional[str] = None
    code: Optional[str] = None
    note: Optional[str] = None

    @field_validator("date")
    @classmethod
    def date_is_valid(cls, v: str) -> str:
        return validate_date(v)

    @field_validator("source")
    @classmethod
    def source_nonempty(cls, v: str) -> str:
        return validate_nonempty(v)

    @model_validator(mode="after")
    def check_positive(self) -> "IncomeCreate":
        if self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


class IncomeUpdate(BaseModel):
    date: Optional[str] = None
    source: Optional[str] = None
    category: Optional[
        Literal["dividend", "interest", "option", "deposit", "withdrawal"]
    ] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    account: Optional[str] = None
    code: Optional[str] = None
    note: Optional[str] = None

    @field_validator("date")
    @classmethod
    def date_is_valid(cls, v: Optional[str]) -> Optional[str]:
        return validate_optional_date(v)

    @model_validator(mode="after")
    def check_positive(self) -> "IncomeUpdate":
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


class IncomeResponse(BaseModel):
    id: int
    date: str
    source: str
    category: Literal["dividend", "interest", "option", "deposit", "withdrawal"]
    amount: float
    currency: str
    account: Optional[str]
    code: Optional[str]
    note: Optional[str]
    create_time: str
    update_time: str
