from sqlalchemy.orm import Session

from fin.models.account import AccountModel
from fin.schemas.account import AccountCreate


class AccountSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[AccountModel]:
        return (
            self._db.query(AccountModel)
            .filter(AccountModel.user_id == user_id)
            .order_by(AccountModel.create_time)
            .all()
        )

    def get_by_id(self, id: int) -> AccountModel | None:
        return self._db.query(AccountModel).filter(AccountModel.id == id).first()

    def create(self, data: AccountCreate, user_id: int) -> AccountModel:
        account = AccountModel(
            user_id=user_id,
            name=data.name,
            currency=data.currency or "CNY",
            note=data.note,
        )
        self._db.add(account)
        self._db.commit()
        self._db.refresh(account)
        return account

    def delete(self, id: int) -> None:
        account = self.get_by_id(id)
        if account:
            self._db.delete(account)
            self._db.commit()
