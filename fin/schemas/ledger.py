from typing import Optional

from pydantic import BaseModel, model_validator


class LedgerCreate(BaseModel):
    direction: str  # "income" | "expense"
    name: str
    date: str
    amount: float
    currency: str = "CNY"
    category: str
    orig_category: Optional[str] = None
    subcategory: Optional[str] = None
    recurring_type: Optional[str] = None
    is_expired: bool = False
    expiry_date: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def check_positive(self) -> "LedgerCreate":
        if self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


class LedgerUpdate(BaseModel):
    direction: Optional[str] = None
    name: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    orig_category: Optional[str] = None
    subcategory: Optional[str] = None
    recurring_type: Optional[str] = None
    is_expired: Optional[bool] = None
    expiry_date: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def check_positive(self) -> "LedgerUpdate":
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


class LedgerResponse(BaseModel):
    id: int
    direction: str
    name: str
    date: str
    amount: float
    currency: str
    category: str
    orig_category: Optional[str]
    subcategory: Optional[str]
    recurring_type: Optional[str]
    is_expired: bool
    expiry_date: Optional[str]
    note: Optional[str]
    create_time: str
    update_time: str
    # Populated only by /api/ledger/recurring — number of records in the dedup'd series
    count: Optional[int] = None


class LedgerListResponse(BaseModel):
    items: list[LedgerResponse]
    total: int
    page: int
    pages: int


class LedgerStatBar(BaseModel):
    date: str
    amount: float


class LedgerStatPie(BaseModel):
    category: str
    amount: float


class LedgerSummary(BaseModel):
    income: float
    expense: float
    net: float
    max_expense: float


class LedgerStatsResponse(BaseModel):
    bars: list[LedgerStatBar]
    pie: list[LedgerStatPie]
    summary: LedgerSummary
