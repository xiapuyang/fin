from datetime import datetime

from sqlalchemy import Column, DateTime, String

from fin.database import Base

MOCK_USER_ID = "00000000-0000-0000-0000-000000000001"


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
