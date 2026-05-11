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


def _migrate_alerts_to_int_id(db: "Session") -> None:
    """Drop alerts / alert_fires tables if they still use UUID (TEXT) primary keys.

    SQLite cannot ALTER column types, so we drop both tables and let create_all
    recreate them with INTEGER primary keys. Existing alert rows are lost, which
    is acceptable for this personal tool.
    """
    from sqlalchemy import text

    cols = {r[1]: r[2].upper() for r in db.execute(text("PRAGMA table_info(alerts)"))}
    if any(
        cols.get("id", "INTEGER").startswith(t)
        for t in ("TEXT", "VARCHAR", "STRING", "CHAR")
    ):
        db.execute(text("DROP TABLE IF EXISTS alert_fires"))
        db.execute(text("DROP TABLE IF EXISTS alerts"))
        db.commit()


_KNOWN_TABLES = {
    "income",
    "holdings",
    "transactions",
    "accounts",
    "alerts",
    "stocks",
    "balance_accounts",
    "balance_snapshots",
    "balance_items",
}


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
        ("stocks", "asset_type", "ALTER TABLE stocks ADD COLUMN asset_type TEXT"),
        ("stocks", "regular_close", "ALTER TABLE stocks ADD COLUMN regular_close REAL"),
        ("accounts", "cutoff_date", "ALTER TABLE accounts ADD COLUMN cutoff_date TEXT"),
        ("watchlist", "user_id", "ALTER TABLE watchlist ADD COLUMN user_id BIGINT"),
        (
            "balance_items",
            "account_id",
            "ALTER TABLE balance_items ADD COLUMN account_id INTEGER",
        ),
        (
            "balance_items",
            "sub_account_id",
            "ALTER TABLE balance_items ADD COLUMN sub_account_id INTEGER",
        ),
    ]
    _KNOWN_TABLES.add("watchlist")
    for table, col, stmt in pending:
        assert table in _KNOWN_TABLES, f"unexpected table name: {table!r}"
        cols = [row[1] for row in db.execute(text(f"PRAGMA table_info({table})"))]
        if col not in cols:
            db.execute(text(stmt))
    db.commit()


def _backfill_watchlist_user_id(db: "Session") -> None:
    """Backfill user_id = MOCK_USER_ID for watchlist rows added before the column existed."""
    from fin.models.user import MOCK_USER_ID
    from sqlalchemy import text

    cols = [row[1] for row in db.execute(text("PRAGMA table_info(watchlist)"))]
    if "user_id" in cols:
        db.execute(
            text("UPDATE watchlist SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": MOCK_USER_ID},
        )
        db.commit()


def _migrate_ledger_schema(db: "Session") -> None:
    """Rename subcategory → orig_category and add new user-defined subcategory column."""
    from sqlalchemy import text

    def cols():
        return [row[1] for row in db.execute(text("PRAGMA table_info(ledger)"))]

    current = cols()
    if not current:
        return  # table not yet created; create_all will use the new model
    if "subcategory" in current and "orig_category" not in current:
        db.execute(
            text("ALTER TABLE ledger RENAME COLUMN subcategory TO orig_category")
        )
        db.commit()
        current = cols()
    if "subcategory" not in current:
        db.execute(text("ALTER TABLE ledger ADD COLUMN subcategory VARCHAR"))
        db.commit()
        current = cols()
    if "amounts_json" not in current:
        db.execute(text("ALTER TABLE ledger ADD COLUMN amounts_json TEXT"))
        db.commit()


def _migrate_category_ids(db: "Session") -> None:
    """Backfill ledger.category from name strings to sequential IDs.

    Rows whose category is already a 4-digit ID are skipped (idempotent).
    Unrecognised names are left unchanged.
    """
    from sqlalchemy import text
    from fin.ledger_categories import BUILTIN_CATEGORY_IDS
    from fin.categories_store import _load_custom

    cols = [row[1] for row in db.execute(text("PRAGMA table_info(ledger)"))]
    if "category" not in cols:
        return

    # Build (direction, name) → id mapping
    name_to_id: dict[tuple[str, str], str] = {}
    for direction, names in BUILTIN_CATEGORY_IDS.items():
        for name, cat_id in names.items():
            name_to_id[(direction, name)] = cat_id
    for c in _load_custom():
        d, n, cid = c.get("direction"), c.get("name"), c.get("id")
        if d and n and cid:
            name_to_id[(d, n)] = cid

    import re

    rows = db.execute(text("SELECT id, direction, category FROM ledger")).fetchall()
    updated = 0
    for row_id, direction, category in rows:
        if category and re.fullmatch(r"0\d{3}", category):
            continue  # already an ID
        cat_id = name_to_id.get((direction, category))
        if cat_id:
            db.execute(
                text("UPDATE ledger SET category = :cid WHERE id = :rid"),
                {"cid": cat_id, "rid": row_id},
            )
            updated += 1
    if updated:
        db.commit()


def _backfill_recurring_subcategory(db: "Session") -> None:
    """Initialize subcategory = name for recurring items missing a subcategory.

    Recurring items use (recurring_type, category, subcategory, amount) as the
    dedup key — name is a sensible default identity when subcategory is unset.
    """
    from sqlalchemy import text

    cols = [row[1] for row in db.execute(text("PRAGMA table_info(ledger)"))]
    if "subcategory" not in cols:
        return
    db.execute(
        text(
            "UPDATE ledger SET subcategory = name "
            "WHERE recurring_type IS NOT NULL AND subcategory IS NULL"
        )
    )
    db.commit()


def _migrate_indexes(db: "Session") -> None:
    """Idempotently create unique indexes for deduplication."""
    from sqlalchemy import text

    indexes = [
        (
            "uq_income_dedup",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_income_dedup "
            "ON income(user_id, date, source, amount, currency)",
        ),
        (
            "uq_txn_dedup",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_txn_dedup "
            "ON transactions(user_id, date, code, side, shares, price, currency)",
        ),
        (
            "uq_account_name",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_account_name "
            "ON accounts(user_id, name)",
        ),
        (
            "uq_holding_snapshot",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_holding_snapshot "
            "ON holdings(user_id, account, code, snapshot_name)",
        ),
        (
            "uq_watchlist_user_symbol",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_user_symbol "
            "ON watchlist(user_id, symbol)",
        ),
        (
            "ix_users_email",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email)",
        ),
        (
            "uq_ledger_dedup",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_dedup "
            "ON ledger(user_id, direction, name, date, amount)",
        ),
        (
            "ix_ledger_user_date",
            "CREATE INDEX IF NOT EXISTS ix_ledger_user_date ON ledger(user_id, date)",
        ),
    ]
    existing = {
        row[1]
        for row in db.execute(
            text("SELECT type, name FROM sqlite_master WHERE type='index'")
        )
    }
    for name, stmt in indexes:
        if name not in existing:
            try:
                db.execute(text(stmt))
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning("Index %s skipped: %s", name, exc)
    db.commit()


def _migrate_balance_indexes(db: "Session") -> None:
    """Create COALESCE-based unique indexes for balance tables.

    SQLAlchemy's Index() cannot express COALESCE(), so these are raw SQL.
    Any existing non-unique index with the same name is dropped first so the
    unique version can be created on both new and upgraded databases.
    """
    from sqlalchemy import text

    # Drop old non-unique versions that block the unique COALESCE indexes
    for name in ("uq_balance_item", "uq_balance_account"):
        row = db.execute(
            text("SELECT sql FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": name},
        ).first()
        if row and row[0] and "UNIQUE" not in row[0].upper():
            db.execute(text(f"DROP INDEX {name}"))
    db.commit()

    indexes = [
        (
            "uq_balance_snapshot",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_balance_snapshot "
            "ON balance_snapshots(user_id, snapshot_date, label)",
        ),
        (
            "uq_balance_account",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_balance_account "
            "ON balance_accounts(user_id, COALESCE(parent_id,-1), name)",
        ),
        (
            "uq_balance_item",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_balance_item "
            "ON balance_items(snapshot_id, side, COALESCE(account_id,-1), "
            "COALESCE(sub_account_id,-1), category)",
        ),
    ]
    existing = {
        row[1]
        for row in db.execute(
            text("SELECT type, name FROM sqlite_master WHERE type='index'")
        )
    }
    for name, stmt in indexes:
        if name not in existing:
            try:
                db.execute(text(stmt))
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Balance index %s skipped: %s", name, exc
                )
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
    import fin.models.ledger  # noqa: F401
    import fin.models.balance_account  # noqa: F401
    import fin.models.balance_snapshot  # noqa: F401
    import fin.models.balance_item  # noqa: F401

    db: Session = SessionLocal()
    try:
        _migrate_alerts_to_int_id(db)
    finally:
        db.close()

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        _seed_mock_user(db)
        _migrate_alert_user_id(db)
        _migrate_columns(db)
        _migrate_ledger_schema(db)
        _migrate_category_ids(db)
        _backfill_recurring_subcategory(db)
        _backfill_watchlist_user_id(db)
        _migrate_indexes(db)
        _migrate_balance_indexes(db)
    finally:
        db.close()
