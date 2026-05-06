from pydantic import BaseModel, Field, model_validator


class LedgerCreate(BaseModel):
    direction: str = Field(pattern="^(income|expense)$")
    name: str
    date: str
    amount: float
    currency: str = "CNY"
    category: str
    orig_category: str | None = None
    subcategory: str | None = None
    recurring_type: str | None = None
    is_expired: bool = False
    expiry_date: str | None = None
    note: str | None = None
    amounts_json: str | None = None  # JSON: {CNY, USD, CAD, HKD} at entry time

    @model_validator(mode="after")
    def check_positive(self) -> "LedgerCreate":
        if self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


class LedgerUpdate(BaseModel):
    direction: str | None = None
    name: str | None = None
    date: str | None = None
    amount: float | None = None
    currency: str | None = None
    category: str | None = None
    orig_category: str | None = None
    subcategory: str | None = None
    recurring_type: str | None = None
    is_expired: bool | None = None
    expiry_date: str | None = None
    note: str | None = None
    amounts_json: str | None = None

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
    category: str  # stable ID e.g. "0001"
    category_name: str  # resolved display name e.g. "餐饮"
    orig_category: str | None
    subcategory: str | None
    recurring_type: str | None
    is_expired: bool
    expiry_date: str | None
    note: str | None
    amounts_json: str | None = None
    create_time: str
    update_time: str
    # Populated only by /api/ledger/recurring — number of records in the dedup'd series
    count: int | None = None


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
    max_expense_name: str | None = None
    max_expense_date: str | None = None
    max_expense_currency: str | None = None


class LedgerStatsResponse(BaseModel):
    bars: list[LedgerStatBar]
    pie: list[LedgerStatPie]
    summary: LedgerSummary


class LedgerImportSkipped(BaseModel):
    row: int
    name: str
    reason: str


class LedgerImportResponse(BaseModel):
    imported: int
    skipped: list[LedgerImportSkipped]
