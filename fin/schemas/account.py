from typing import Optional

from pydantic import BaseModel


class AccountCreate(BaseModel):
    name: str
    currency: str = "CNY"
    note: Optional[str] = None
    cutoff_date: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    note: Optional[str] = None
    cutoff_date: Optional[str] = None


class AccountResponse(BaseModel):
    id: int
    name: str
    currency: str
    note: Optional[str]
    cutoff_date: Optional[str]
    create_time: str
    update_time: str
