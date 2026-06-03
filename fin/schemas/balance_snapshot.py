from pydantic import BaseModel, field_validator

from fin.schemas._validators import (
    validate_date,
    validate_nonempty,
    validate_optional_date,
)


class BalanceSnapshotCreate(BaseModel):
    snapshot_date: str
    label: str
    note: str | None = None

    @field_validator("snapshot_date")
    @classmethod
    def snapshot_date_is_valid(cls, v: str) -> str:
        return validate_date(v)

    @field_validator("label")
    @classmethod
    def label_nonempty(cls, v: str) -> str:
        return validate_nonempty(v)


class BalanceSnapshotUpdate(BaseModel):
    snapshot_date: str | None = None
    label: str | None = None
    note: str | None = None

    @field_validator("snapshot_date")
    @classmethod
    def snapshot_date_is_valid(cls, v: str | None) -> str | None:
        return validate_optional_date(v)


class BalanceSnapshotResponse(BaseModel):
    id: int
    snapshot_date: str
    label: str
    note: str | None
    item_count: int
    create_time: str
    update_time: str
