from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.balance_account import BalanceAccountModel
from fin.schemas.balance_account import (
    BalanceAccountBulkItem,
    BalanceAccountCreate,
    BalanceAccountUpdate,
)


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

    def bulk_create_with_parent_names(
        self,
        items: list[BalanceAccountBulkItem],
        user_id: int,
    ) -> tuple[int, int]:
        """Insert many accounts; resolve parents by name within the batch.

        Two-phase in one transaction: root rows (parent_name is None) are
        inserted and flushed first so child rows can look up parent_ids in
        the same transaction. All child `parent_name` references are validated
        against the union of existing roots + newly created roots before any
        child insert. Unknown parent → rollback + raise ValueError (caller
        maps to HTTP 400).

        Dedup key: (name, parent_id). Duplicates are counted as skipped.

        Args:
            items: Bulk payload rows.
            user_id: Owner user id.

        Returns:
            (created, skipped) counts.

        Raises:
            ValueError: One or more child `parent_name` values cannot be
                resolved. The transaction is rolled back before raising.
        """
        existing = self.get_all(user_id)
        by_key: dict[tuple[str, int | None], int] = {
            (a.name, a.parent_id): a.id for a in existing
        }
        root_name_to_id: dict[str, int] = {
            a.name: a.id for a in existing if a.parent_id is None
        }

        roots = [i for i in items if i.parent_name is None]
        children = [i for i in items if i.parent_name is not None]

        created = 0
        skipped = 0

        for item in roots:
            if (item.name, None) in by_key:
                skipped += 1
                continue
            new = BalanceAccountModel(user_id=user_id, name=item.name)
            self._db.add(new)
            self._db.flush()
            by_key[(item.name, None)] = new.id
            root_name_to_id[item.name] = new.id
            created += 1

        missing = sorted(
            {i.parent_name for i in children if i.parent_name not in root_name_to_id}
        )
        if missing:
            self._db.rollback()
            raise ValueError(f"unknown parent_name(s): {missing}")

        for item in children:
            parent_id = root_name_to_id[item.parent_name]
            if (item.name, parent_id) in by_key:
                skipped += 1
                continue
            new = BalanceAccountModel(
                user_id=user_id, name=item.name, parent_id=parent_id
            )
            self._db.add(new)
            self._db.flush()
            by_key[(item.name, parent_id)] = new.id
            created += 1

        self._db.commit()
        return created, skipped

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
        """Delete account; nullify all references to it across balance_items and accounts."""
        from fin.models.account import AccountModel
        from fin.models.balance_item import BalanceItemModel

        row = self.get_by_id(account_id, user_id)
        children = (
            self._db.query(BalanceAccountModel)
            .filter(
                BalanceAccountModel.parent_id == account_id,
                BalanceAccountModel.user_id == user_id,
            )
            .count()
        )
        if children:
            raise ValueError(f"account {account_id} has child accounts")

        # Nullify refs in balance_items
        self._db.query(BalanceItemModel).filter(
            BalanceItemModel.account_id == account_id,
            BalanceItemModel.user_id == user_id,
        ).update({"account_id": None})
        self._db.query(BalanceItemModel).filter(
            BalanceItemModel.sub_account_id == account_id,
            BalanceItemModel.user_id == user_id,
        ).update({"sub_account_id": None})
        # Nullify refs in broker/wallet accounts table
        self._db.query(AccountModel).filter(
            AccountModel.balance_account_id == account_id,
            AccountModel.user_id == user_id,
        ).update({"balance_account_id": None})
        self._db.query(AccountModel).filter(
            AccountModel.balance_sub_account_id == account_id,
            AccountModel.user_id == user_id,
        ).update({"balance_sub_account_id": None})
        self._db.delete(row)
        self._db.commit()
