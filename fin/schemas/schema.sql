-- fin database schema
-- Source of truth: fin/models/*.py + fin/database.py migrations
-- Recreate: sqlite3 data/fin.db < schema.sql

-- ── users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    name        VARCHAR  NOT NULL,
    email       VARCHAR  NOT NULL UNIQUE,
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL
);

-- ── accounts ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    id           INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id      BIGINT,
    name         VARCHAR  NOT NULL,
    currency     TEXT     DEFAULT 'CNY',
    note         VARCHAR,
    cutoff_date  TEXT,        -- ignore transactions before this date (e.g. pre-transfer backup rows)
    create_time  DATETIME NOT NULL,
    update_time  DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_account_name ON accounts (user_id, name);

-- ── holdings (position snapshots) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS holdings (
    id            INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id       BIGINT,
    code          VARCHAR NOT NULL,
    name          VARCHAR,
    market        VARCHAR NOT NULL,
    currency      VARCHAR NOT NULL,
    account       TEXT,
    snapshot_name TEXT,    -- groups rows into a named snapshot (e.g. "2024-09-01")
    as_of_date    VARCHAR, -- baseline date; only transactions after this stack on top
    shares        FLOAT   NOT NULL DEFAULT 0.0,
    avg_cost      FLOAT   NOT NULL DEFAULT 0.0,
    note          VARCHAR,
    create_time   DATETIME NOT NULL,
    update_time   DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_holding_snapshot
    ON holdings (user_id, account, code, snapshot_name);

-- ── transactions (buys/sells) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id     BIGINT,
    date        VARCHAR NOT NULL,
    code        VARCHAR NOT NULL,
    name        VARCHAR,
    side        VARCHAR NOT NULL,  -- 'buy' | 'sell'
    shares      FLOAT   NOT NULL DEFAULT 0.0,
    price       FLOAT   NOT NULL DEFAULT 0.0,
    currency    VARCHAR NOT NULL DEFAULT 'USD',
    account     TEXT,
    realized    FLOAT,             -- realised P&L for sell trades (CNY)
    note        VARCHAR,
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL
);
-- Prevents duplicate rows when the same CSV is imported twice
CREATE UNIQUE INDEX IF NOT EXISTS uq_txn_dedup
    ON transactions (user_id, date, code, side, shares, price, currency);

-- ── income (dividends, interest, option premiums, deposits, withdrawals) ───────
CREATE TABLE IF NOT EXISTS income (
    id          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id     BIGINT,
    date        VARCHAR NOT NULL,
    source      VARCHAR NOT NULL,
    category    VARCHAR NOT NULL,  -- 'dividend' | 'interest' | 'option' | 'deposit' | 'withdrawal'
    amount      FLOAT   NOT NULL,
    currency    VARCHAR NOT NULL DEFAULT 'USD',
    account     TEXT,
    code        TEXT,
    note        VARCHAR,
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL
);
-- Prevents duplicate rows when the same CSV is imported twice
CREATE UNIQUE INDEX IF NOT EXISTS uq_income_dedup
    ON income (user_id, date, source, amount, currency);

-- ── alerts ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    symbol     VARCHAR NOT NULL,
    name       VARCHAR NOT NULL,
    condition  VARCHAR NOT NULL,  -- 'price_gte' | 'price_lte' | 'change_gte' | 'change_lte'
    value      FLOAT   NOT NULL,
    enabled    BOOLEAN NOT NULL DEFAULT 1,
    user_id    BIGINT,
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_fires (
    id         INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    alert_id   INTEGER NOT NULL,
    fired_at   DATETIME NOT NULL,
    price      FLOAT NOT NULL,
    change_pct FLOAT NOT NULL
);

-- ── stocks (price cache) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stocks (
    symbol          VARCHAR NOT NULL PRIMARY KEY,
    name            VARCHAR,
    currency        VARCHAR,
    price           FLOAT,
    prev_close      FLOAT,
    open_price      FLOAT,
    high            FLOAT,
    low             FLOAT,
    volume          FLOAT,
    amount          FLOAT,
    turnover_rate   FLOAT,
    pe_ttm          FLOAT,
    pe_dynamic      FLOAT,
    pb              FLOAT,
    market_cap      FLOAT,
    total_shares    FLOAT,
    float_shares    FLOAT,
    float_market_cap FLOAT,
    week_52_high    FLOAT,
    week_52_low     FLOAT,
    beta            FLOAT,
    dividend_ttm    FLOAT,
    dividend_rate   FLOAT,
    asset_type      VARCHAR,
    updated_at      DATETIME NOT NULL
);

-- ── watchlist ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist (
    id          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id     BIGINT,
    symbol      VARCHAR NOT NULL,
    name        VARCHAR,
    market      VARCHAR,
    currency    VARCHAR,
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_user_symbol ON watchlist (user_id, symbol);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);
