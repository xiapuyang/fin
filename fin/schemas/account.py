from typing import Optional

from pydantic import BaseModel, field_validator

from fin.schemas._validators import validate_nonempty, validate_optional_date


class AccountCreate(BaseModel):
    name: str
    currency: str = "CNY"
    note: Optional[str] = None
    cutoff_date: Optional[str] = None
    benchmark_enabled: bool = False

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, v: str) -> str:
        return validate_nonempty(v)

    @field_validator("cutoff_date")
    @classmethod
    def cutoff_date_is_valid(cls, v: Optional[str]) -> Optional[str]:
        return validate_optional_date(v)


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    note: Optional[str] = None
    cutoff_date: Optional[str] = None
    balance_account_id: Optional[int] = None
    balance_sub_account_id: Optional[int] = None
    symbol_markets: Optional[dict[str, str]] = None
    benchmark_enabled: Optional[bool] = None
    benchmark_schemes: Optional[dict] = None

    @field_validator("cutoff_date")
    @classmethod
    def cutoff_date_is_valid(cls, v: Optional[str]) -> Optional[str]:
        return validate_optional_date(v)


class AccountResponse(BaseModel):
    id: int
    name: str
    currency: str
    note: Optional[str]
    cutoff_date: Optional[str]
    balance_account_id: Optional[int]
    balance_sub_account_id: Optional[int]
    symbol_markets: Optional[dict]
    benchmark_enabled: bool
    benchmark_schemes: Optional[dict]
    create_time: str
    update_time: str
