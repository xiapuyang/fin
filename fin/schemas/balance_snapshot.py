from pydantic import BaseModel


class BalanceSnapshotCreate(BaseModel):
    snapshot_date: str
    label: str
    note: str | None = None


class BalanceSnapshotUpdate(BaseModel):
    snapshot_date: str | None = None
    label: str | None = None
    note: str | None = None


class BalanceSnapshotResponse(BaseModel):
    id: int
    snapshot_date: str
    label: str
    note: str | None
    item_count: int
    create_time: str
    update_time: str
