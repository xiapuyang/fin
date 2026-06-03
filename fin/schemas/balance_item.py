from pydantic import BaseModel, field_validator

from fin.schemas._validators import validate_nonempty, validate_optional_date

BALANCE_CATEGORIES = {
    "现金",
    "存款",
    "理财",
    "投资",
    "期权",
    "固定资产",
    "房产",
    "社保",
    "外债",
    "信用卡",
    "贷款",
    "其他贷款",
}


class BalanceItemCreate(BaseModel):
    snapshot_id: int
    name: str
    category: str
    side: str
    amount: float
    currency: str = "CNY"
    account_id: int | None = None
    sub_account_id: int | None = None
    note: str | None = None
    price: float | None = None
    quantity: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    interest_rate: float | None = None
    monthly_payment: float | None = None

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, v: str) -> str:
        return validate_nonempty(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in BALANCE_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(BALANCE_CATEGORIES)}")
        return v

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v not in ("asset", "liability"):
            raise ValueError("side must be 'asset' or 'liability'")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def dates_are_valid(cls, v: str | None) -> str | None:
        return validate_optional_date(v)


class BalanceItemUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    side: str | None = None
    amount: float | None = None
    currency: str | None = None
    account_id: int | None = None
    sub_account_id: int | None = None
    note: str | None = None
    price: float | None = None
    quantity: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    interest_rate: float | None = None
    monthly_payment: float | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in BALANCE_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(BALANCE_CATEGORIES)}")
        return v

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str | None) -> str | None:
        if v is not None and v not in ("asset", "liability"):
            raise ValueError("side must be 'asset' or 'liability'")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def dates_are_valid(cls, v: str | None) -> str | None:
        return validate_optional_date(v)


class BalanceItemResponse(BaseModel):
    id: int
    snapshot_id: int
    snapshot_date: str  # denormalized for history modal convenience
    account_id: int | None
    sub_account_id: int | None
    account_name: str | None  # resolved from balance_accounts
    sub_account_name: str | None  # resolved from balance_accounts
    category: str
    side: str
    name: str
    amount: float
    currency: str
    note: str | None
    price: float | None
    quantity: float | None
    start_date: str | None
    end_date: str | None
    interest_rate: float | None
    monthly_payment: float | None
    create_time: str
    update_time: str
