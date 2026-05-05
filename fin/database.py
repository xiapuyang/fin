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
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _seed_mock_user(db: "Session") -> None:
    """Insert the single mock user if it does not already exist.

    Args:
        db: Active SQLAlchemy session.
    """
    from fin.models.user import UserModel, MOCK_USER_ID

    if not db.query(UserModel).filter(UserModel.email == "admin@fin.local").first():
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


_KNOWN_TABLES = {"income", "holdings", "transactions", "accounts", "alerts"}


def _migrate_columns(db: "Session") -> None:
    """Idempotently add new columns across all tables."""
    from sqlalchemy import text

    pending = [
        ("income", "code", "ALTER TABLE income ADD COLUMN code TEXT"),
        ("income", "account", "ALTER TABLE income ADD COLUMN account TEXT"),
        ("holdings", "account", "ALTER TABLE holdings ADD COLUMN account TEXT"),
        (
            "holdings",
            "snapshot_name",
            "ALTER TABLE holdings ADD COLUMN snapshot_name TEXT",
        ),
        ("transactions", "account", "ALTER TABLE transactions ADD COLUMN account TEXT"),
        (
            "accounts",
            "currency",
            "ALTER TABLE accounts ADD COLUMN currency TEXT DEFAULT 'CNY'",
        ),
    ]
    for table, col, stmt in pending:
        assert table in _KNOWN_TABLES, f"unexpected table name: {table!r}"
        cols = [row[1] for row in db.execute(text(f"PRAGMA table_info({table})"))]
        if col not in cols:
            db.execute(text(stmt))
    db.commit()


def init_db() -> None:
    import fin.models.alert  # noqa: F401
    import fin.models.stock  # noqa: F401
    import fin.models.user  # noqa: F401
    import fin.models.watchlist  # noqa: F401
    import fin.models.account  # noqa: F401
    import fin.models.holding  # noqa: F401
    import fin.models.income  # noqa: F401
    import fin.models.transaction  # noqa: F401

    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        _seed_mock_user(db)
        _migrate_alert_user_id(db)
        _migrate_columns(db)
    finally:
        db.close()
