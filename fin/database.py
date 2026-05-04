from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from fin.config import DB_PATH


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_mock_user(db: "Session") -> None:
    """Insert the single mock user if it does not already exist.

    Args:
        db: Active SQLAlchemy session.
    """
    from fin.models.user import UserModel, MOCK_USER_ID

    if not db.query(UserModel).filter(UserModel.id == MOCK_USER_ID).first():
        db.add(UserModel(id=MOCK_USER_ID, name="Sharp", email="admin@fin.local"))
        db.commit()


def _migrate_alert_user_id(db: "Session") -> None:
    """Add user_id column to alerts table and backfill existing rows.

    Idempotent: checks for the column before altering. Uses bound parameters
    for the backfill UPDATE to avoid f-string SQL injection patterns.

    Args:
        db: Active SQLAlchemy session.
    """
    from fin.models.user import MOCK_USER_ID
    from sqlalchemy import text

    cols = [row[1] for row in db.execute(text("PRAGMA table_info(alerts)"))]
    if "user_id" not in cols:
        db.execute(text("ALTER TABLE alerts ADD COLUMN user_id INTEGER"))
        db.execute(
            text("UPDATE alerts SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": MOCK_USER_ID},
        )
        db.commit()
    elif db.execute(text("SELECT 1 FROM alerts WHERE user_id IS NULL LIMIT 1")).first():
        db.execute(
            text("UPDATE alerts SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": MOCK_USER_ID},
        )
        db.commit()


def init_db() -> None:
    from fin.models import alert, stock, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        _seed_mock_user(db)
        _migrate_alert_user_id(db)
    finally:
        db.close()
