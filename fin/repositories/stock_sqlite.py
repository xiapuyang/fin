from datetime import datetime

from sqlalchemy.orm import Session

from fin.models.stock import StockModel


class StockSQLiteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_symbol(self, symbol: str) -> StockModel | None:
        return self._db.query(StockModel).filter(StockModel.symbol == symbol).first()

    def get_all(self) -> list[StockModel]:
        return self._db.query(StockModel).all()

    def upsert(self, symbol: str, data: dict) -> StockModel:
        stock = self.get_by_symbol(symbol)
        if stock is None:
            stock = StockModel(symbol=symbol)
            self._db.add(stock)
        for key, val in data.items():
            if hasattr(stock, key) and val is not None:
                setattr(stock, key, val)
        stock.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(stock)
        return stock
