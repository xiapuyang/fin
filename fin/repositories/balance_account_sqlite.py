from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.balance_account import BalanceAccountModel
from fin.schemas.balance_account import BalanceAccountCreate, BalanceAccountUpdate


class BalanceAccountSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[BalanceAccountModel]:
        return (
            self._db.query(BalanceAccountModel)
            .filter(BalanceAccountModel.user_id == user_id)
            .order_by(BalanceAccountModel.id)
            .all()
        )

    def get_by_id(self, account_id: int, user_id: int) -> BalanceAccountModel:
        row = (
            self._db.query(BalanceAccountModel)
            .filter(
                BalanceAccountModel.id == account_id,
                BalanceAccountModel.user_id == user_id,
            )
            .first()
        )
        if not row:
            raise ValueError(f"balance_account {account_id} not found")
        return row

    def create(self, data: BalanceAccountCreate, user_id: int) -> BalanceAccountModel:
        row = BalanceAccountModel(user_id=user_id, **data.model_dump())
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def update(
        self, account_id: int, data: BalanceAccountUpdate, user_id: int
    ) -> BalanceAccountModel:
        row = self.get_by_id(account_id, user_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        row.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(row)
        return row

    def delete(self, account_id: int, user_id: int) -> None:
        """Delete account; nullify account_id/sub_account_id refs on balance_items."""
        from fin.models.balance_item import BalanceItemModel

        self._db.query(BalanceItemModel).filter(
            BalanceItemModel.account_id == account_id,
            BalanceItemModel.user_id == user_id,
        ).update({"account_id": None})
        self._db.query(BalanceItemModel).filter(
            BalanceItemModel.sub_account_id == account_id,
            BalanceItemModel.user_id == user_id,
        ).update({"sub_account_id": None})
        row = self.get_by_id(account_id, user_id)
        self._db.delete(row)
        self._db.commit()
