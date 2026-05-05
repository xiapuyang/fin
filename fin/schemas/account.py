from typing import Optional

from pydantic import BaseModel


class AccountCreate(BaseModel):
    name: str
    currency: str = "CNY"
    note: Optional[str] = None


class AccountResponse(BaseModel):
    id: int
    name: str
    currency: str
    note: Optional[str]
    create_time: str
    update_time: str
