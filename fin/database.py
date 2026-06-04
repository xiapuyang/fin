from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from fin.config import DB_PATH


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={
        "check_same_thread": False,
        # Wait up to 5s for a write lock instead of raising SQLITE_BUSY.
        # Required because /api/prices fans out to a ThreadPoolExecutor where
        # each worker opens its own SessionLocal and upserts the stock cache.
        "timeout": 5.0,
    },
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
        db.add(UserModel(id=MOCK_USER_ID, name="User", email="admin@fin.local"))
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
    "alert_fires",
    "stocks",
    "balance_accounts",
    "balance_snapshots",
    "balance_items",
    "price_history",
    "benchmark_results",
    "benchmark_custom_schemes",
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
        (
            "accounts",
            "symbol_markets",
            "ALTER TABLE accounts ADD COLUMN symbol_markets TEXT",
        ),
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
        (
            "alert_fires",
            "condition",
            "ALTER TABLE alert_fires ADD COLUMN condition VARCHAR",
        ),
        (
            "alert_fires",
            "value",
            "ALTER TABLE alert_fires ADD COLUMN value FLOAT",
        ),
        (
            "accounts",
            "benchmark_enabled",
            "ALTER TABLE accounts ADD COLUMN benchmark_enabled TEXT DEFAULT '0'",
        ),
        (
            "accounts",
            "benchmark_schemes",
            "ALTER TABLE accounts ADD COLUMN benchmark_schemes TEXT",
        ),
        (
            "benchmark_custom_schemes",
            "enabled",
            "ALTER TABLE benchmark_custom_schemes ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1",
        ),
        (
            "benchmark_custom_schemes",
            "is_portfolio_snapshot",
            "ALTER TABLE benchmark_custom_schemes ADD COLUMN is_portfolio_snapshot INTEGER NOT NULL DEFAULT 0",
        ),
    ]
    _KNOWN_TABLES.add("watchlist")
    for table, col, stmt in pending:
        if table not in _KNOWN_TABLES:
            raise ValueError(f"unknown table: {table}")
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


def _backfill_alert_fire_snapshot(db: "Session") -> None:
    """Backfill condition/value on pre-snapshot fires using the parent alert's current values.

    Best-effort only: if the alert's threshold was edited between fire and now, the
    backfilled value will not match the historical truth. New fires (post-migration)
    write their own snapshot at creation time.
    """
    from sqlalchemy import text

    cols = [row[1] for row in db.execute(text("PRAGMA table_info(alert_fires)"))]
    if "condition" not in cols or "value" not in cols:
        return
    db.execute(
        text(
            "UPDATE alert_fires SET condition = ("
            "  SELECT condition FROM alerts WHERE alerts.id = alert_fires.alert_id"
            ") WHERE condition IS NULL AND EXISTS ("
            "  SELECT 1 FROM alerts WHERE alerts.id = alert_fires.alert_id"
            ")"
        )
    )
    db.execute(
        text(
            "UPDATE alert_fires SET value = ("
            "  SELECT value FROM alerts WHERE alerts.id = alert_fires.alert_id"
            ") WHERE value IS NULL AND EXISTS ("
            "  SELECT 1 FROM alerts WHERE alerts.id = alert_fires.alert_id"
            ")"
        )
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
        (
            "uq_price_history_sym_date",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_price_history_sym_date "
            "ON price_history(symbol, date)",
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


def _drop_old_benchmark_results(db: "Session") -> None:
    """Drop benchmark_results if it has the old schema (results_json column).

    The table is recreated by create_all with the new per-bench_id row design.
    Safe to call with no data present.
    """
    from sqlalchemy import text

    cols = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(benchmark_results)")).fetchall()
    }
    if cols and "bench_id" not in cols:
        db.execute(text("DROP TABLE IF EXISTS benchmark_results"))
        db.commit()


def _migrate_benchmark_result_columns(db: "Session") -> None:
    """Add current_value_usd and computed_at columns to benchmark_results if missing."""
    from sqlalchemy import text

    cols = {
        row[1]
        for row in db.execute(text("PRAGMA table_info(benchmark_results)")).fetchall()
    }
    if not cols:
        return
    for col, typedef in [
        ("current_value_usd", "REAL"),
        ("computed_at", "DATETIME"),
    ]:
        if col not in cols:
            db.execute(
                text(f"ALTER TABLE benchmark_results ADD COLUMN {col} {typedef}")
            )
    db.commit()


def _drop_holdings_as_of_date(db: "Session") -> None:
    """Drop the as_of_date column from holdings.

    The column is no longer read by application code; snapshot_name now
    carries the cutoff date directly. This helper is idempotent: it checks
    for the column with PRAGMA before issuing ALTER TABLE.

    Requires SQLite >= 3.35.0 for DROP COLUMN support. On older runtimes,
    or when the database file is locked by another process, the ALTER will
    raise — caught here and logged so server startup is never blocked by a
    schema-cleanup step that can be re-run on the next boot.
    """
    from sqlalchemy import text

    cols = [row[1] for row in db.execute(text("PRAGMA table_info(holdings)"))]
    if "as_of_date" not in cols:
        return
    try:
        db.execute(text("ALTER TABLE holdings DROP COLUMN as_of_date"))
        db.commit()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Dropping holdings.as_of_date skipped: %s", exc
        )
        db.rollback()


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
    import fin.models.dividend_history  # noqa: F401
    import fin.models.price_history  # noqa: F401
    import fin.models.benchmark_result  # noqa: F401
    import fin.models.benchmark_custom_scheme  # noqa: F401

    db: Session = SessionLocal()
    try:
        _migrate_alerts_to_int_id(db)
        _drop_old_benchmark_results(db)
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
        _backfill_alert_fire_snapshot(db)
        _migrate_indexes(db)
        _migrate_balance_indexes(db)
        _drop_holdings_as_of_date(db)
        _migrate_benchmark_result_columns(db)
    finally:
        db.close()
