from pydantic import BaseModel, field_validator


class BalanceAccountCreate(BaseModel):
    name: str
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v


class BalanceAccountUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None


class BalanceAccountResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None
    create_time: str
    update_time: str


class BalanceAccountBulkItem(BaseModel):
    """One row in a bulk balance-account create payload.

    `parent_name` is a forward reference resolved within the batch + existing
    rows. Use None for top-level accounts. Roots are processed first, then
    children — so one level of nesting in a single payload is supported.
    """

    name: str
    parent_name: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v
