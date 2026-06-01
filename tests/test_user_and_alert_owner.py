"""Tests for UserModel seeding and alert ownership."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.database import Base, _seed_mock_user, _migrate_alert_user_id
from fin.models.user import UserModel, MOCK_USER_ID
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin.schemas.alert import AlertCreate


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_seed_mock_user_creates_user(db):
    _seed_mock_user(db)
    user = db.query(UserModel).filter(UserModel.id == MOCK_USER_ID).first()
    assert user is not None
    assert user.name == "User"


def test_seed_mock_user_is_idempotent(db):
    _seed_mock_user(db)
    _seed_mock_user(db)
    count = db.query(UserModel).filter(UserModel.id == MOCK_USER_ID).count()
    assert count == 1


def test_create_alert_sets_mock_user_id(db):
    _seed_mock_user(db)
    repo = AlertSQLiteRepository(db)
    alert = repo.create(
        AlertCreate(symbol="AAPL", name="Test", condition="price_lte", value=100.0)
    )
    assert alert.user_id == MOCK_USER_ID


def test_migrate_alert_user_id_fills_nulls(db):
    _seed_mock_user(db)
    repo = AlertSQLiteRepository(db)
    alert = repo.create(
        AlertCreate(symbol="AAPL", name="Test", condition="price_lte", value=100.0)
    )
    # manually null it out to simulate pre-migration state
    from sqlalchemy import text

    db.execute(text(f"UPDATE alerts SET user_id = NULL WHERE id = '{alert.id}'"))
    db.commit()
    _migrate_alert_user_id(db)
    db.refresh(alert)
    assert alert.user_id == MOCK_USER_ID
