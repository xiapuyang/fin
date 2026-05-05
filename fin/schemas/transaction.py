from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class TransactionCreate(BaseModel):
    date: str
    code: str
    name: Optional[str] = None
    side: Literal["buy", "sell"]
    shares: float = 0.0
    price: float = 0.0
    currency: str = "USD"
    account: Optional[str] = None
    realized: Optional[float] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def check_non_negative(self) -> "TransactionCreate":
        if self.shares < 0:
            raise ValueError("shares must be >= 0")
        if self.price < 0:
            raise ValueError("price must be >= 0")
        return self


class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    side: Optional[Literal["buy", "sell"]] = None
    shares: Optional[float] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    account: Optional[str] = None
    realized: Optional[float] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def check_non_negative(self) -> "TransactionUpdate":
        if self.shares is not None and self.shares < 0:
            raise ValueError("shares must be >= 0")
        if self.price is not None and self.price < 0:
            raise ValueError("price must be >= 0")
        return self


class TransactionResponse(BaseModel):
    id: int
    date: str
    code: str
    name: Optional[str]
    side: Literal["buy", "sell"]
    shares: float
    price: float
    currency: str
    account: Optional[str]
    realized: Optional[float]
    note: Optional[str]
    create_time: str
    update_time: str
