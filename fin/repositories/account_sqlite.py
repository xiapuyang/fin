import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.account import AccountModel
from fin.schemas.account import AccountCreate, AccountUpdate


class AccountSQLiteRepository:
    """SQLite-backed repository for brokerage account records."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[AccountModel]:
        """Return all accounts for a user, ordered by creation time."""
        return (
            self._db.query(AccountModel)
            .filter(AccountModel.user_id == user_id)
            .order_by(AccountModel.create_time)
            .all()
        )

    def get_by_id(self, id: int) -> AccountModel | None:
        """Return a single account by primary key, or None if not found."""
        return self._db.query(AccountModel).filter(AccountModel.id == id).first()

    def create(self, data: AccountCreate, user_id: int) -> AccountModel:
        """Insert a new account and return the persisted model."""
        account = AccountModel(
            user_id=user_id,
            name=data.name,
            currency=data.currency or "CNY",
            note=data.note,
            cutoff_date=data.cutoff_date,
        )
        self._db.add(account)
        self._db.commit()
        self._db.refresh(account)
        return account

    def update(self, id: int, data: AccountUpdate) -> AccountModel | None:
        """Apply a partial update to an account.

        Args:
            id: Primary key of the account to update.
            data: Fields to change; unset fields are left untouched.
                  Explicit null for NOT NULL columns (name, currency) is ignored.

        Returns:
            The updated model, or None if the account does not exist.

        Raises:
            sqlalchemy.exc.IntegrityError: If the new name duplicates an existing account.
        """
        account = self.get_by_id(id)
        if account is None:
            return None
        non_null_fields = {"name", "currency"}
        for field, val in data.model_dump(exclude_unset=True).items():
            if val is None and field in non_null_fields:
                continue
            if field == "symbol_markets":
                setattr(account, field, json.dumps(val) if val is not None else None)
            else:
                setattr(account, field, val)
        account.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(account)
        return account

    def delete(self, id: int) -> None:
        """Delete an account by primary key. No-op if not found."""
        account = self.get_by_id(id)
        if account:
            self._db.delete(account)
            self._db.commit()
