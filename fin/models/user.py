from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, String

from fin.database import Base

MOCK_USER_ID = 1


class UserModel(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
