from pydantic import BaseModel


class BalanceAccountCreate(BaseModel):
    name: str
    parent_id: int | None = None


class BalanceAccountUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None


class BalanceAccountResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None
    create_time: str
    update_time: str
