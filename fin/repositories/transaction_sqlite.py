from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fin.models.transaction import TransactionModel
from fin.schemas.transaction import TransactionCreate, TransactionUpdate


class TransactionSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self, user_id: int) -> list[TransactionModel]:
        return (
            self._db.query(TransactionModel)
            .filter(TransactionModel.user_id == user_id)
            .order_by(TransactionModel.date.desc())
            .all()
        )

    def get_by_id(self, id: int) -> TransactionModel | None:
        return (
            self._db.query(TransactionModel).filter(TransactionModel.id == id).first()
        )

    def create(self, data: TransactionCreate, user_id: int) -> TransactionModel:
        txn = TransactionModel(
            user_id=user_id,
            date=data.date,
            code=data.code,
            name=data.name,
            side=data.side,
            shares=data.shares,
            price=data.price,
            currency=data.currency,
            account=data.account,
            realized=data.realized,
            note=data.note,
        )
        self._db.add(txn)
        self._db.commit()
        self._db.refresh(txn)
        return txn

    def update(self, id: str, data: TransactionUpdate) -> TransactionModel:
        txn = self.get_by_id(id)
        if txn is None:
            raise ValueError(f"Transaction {id} not found")
        for field, val in data.model_dump(exclude_unset=True).items():
            setattr(txn, field, val)
        txn.update_time = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(txn)
        return txn

    def delete(self, id: str) -> None:
        txn = self.get_by_id(id)
        if txn:
            self._db.delete(txn)
            self._db.commit()

    def bulk_create(
        self, rows: list[TransactionCreate], user_id: int
    ) -> list[TransactionModel]:
        models = [
            TransactionModel(
                user_id=user_id,
                date=r.date,
                code=r.code,
                name=r.name,
                side=r.side,
                shares=r.shares,
                price=r.price,
                currency=r.currency,
                account=r.account,
                realized=r.realized,
                note=r.note,
            )
            for r in rows
        ]
        self._db.add_all(models)
        self._db.commit()
        for m in models:
            self._db.refresh(m)
        return models
