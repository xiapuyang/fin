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
    cutoff_date             TEXT,
    balance_account_id      INTEGER,
    balance_sub_account_id  INTEGER,
    symbol_markets          TEXT,      -- JSON: {"013308": "HK"} — per-symbol market classification overrides
    benchmark_enabled       TEXT     DEFAULT '0',  -- '1' = include in benchmark compute
    benchmark_schemes       TEXT,                  -- JSON: [scheme_id, ...] (null = use defaults)
    rebalance_enabled       TEXT     DEFAULT '0',  -- '1' = show per-account rebalance tab
    rebalance_config        TEXT,                  -- JSON: {type, ...} per-account rebalance config
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
    change_pct FLOAT NOT NULL,
    condition  VARCHAR,
    value      FLOAT
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

-- ── ledger (income & expense records) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ledger (
    id              INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id         BIGINT,
    direction       VARCHAR  NOT NULL,   -- 'income' | 'expense'
    name            VARCHAR  NOT NULL,
    date            VARCHAR  NOT NULL,   -- YYYY-MM-DD
    amount          FLOAT    NOT NULL,   -- original amount in original currency
    currency        VARCHAR  NOT NULL DEFAULT 'CNY',
    category        VARCHAR  NOT NULL,
    orig_category   VARCHAR,             -- original import label (e.g. Notion 分类)
    subcategory     VARCHAR,             -- user-defined grouping / series key for recurring
    recurring_type  VARCHAR,             -- 'monthly' | 'annual' | 'semi_annual' | 'every_4months'
    is_expired      BOOLEAN  NOT NULL DEFAULT 0,
    expiry_date     VARCHAR,             -- YYYY-MM-DD when a recurring item was ended
    note            VARCHAR,
    amounts_json    TEXT,                -- JSON snapshot: {CNY, USD, CAD, HKD} at entry time
    create_time     DATETIME NOT NULL,
    update_time     DATETIME NOT NULL,
    UNIQUE (user_id, direction, name, date, amount)   -- uq_ledger_dedup
);

-- ── balance_accounts (account hierarchy for balance sheet) ────────────────────
CREATE TABLE IF NOT EXISTS balance_accounts (
    id          INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id     BIGINT,
    name        VARCHAR  NOT NULL,
    parent_id   INTEGER,             -- NULL = top-level account; set = sub-account
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL
);
-- COALESCE makes NULL parent_id comparable so top-level accounts are also deduplicated
CREATE UNIQUE INDEX IF NOT EXISTS uq_balance_account
    ON balance_accounts (user_id, COALESCE(parent_id, -1), name);

-- ── balance_snapshots (point-in-time net worth snapshots) ─────────────────────
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id            INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id       BIGINT,
    snapshot_date VARCHAR  NOT NULL,  -- YYYY-MM-DD
    label         VARCHAR  NOT NULL,
    note          VARCHAR,
    create_time   DATETIME NOT NULL,
    update_time   DATETIME NOT NULL,
    UNIQUE (user_id, snapshot_date, label)  -- uq_balance_snapshot
);

-- ── balance_items (line items within a snapshot) ──────────────────────────────
CREATE TABLE IF NOT EXISTS balance_items (
    id              INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,
    user_id         BIGINT,
    account_id      INTEGER,          -- FK-less ref to balance_accounts.id
    sub_account_id  INTEGER,          -- FK-less ref to balance_accounts.id (child)
    category        VARCHAR NOT NULL, -- 现金|理财|投资|期权|固定资产|房产|社保|外债|信用卡|贷款|其他贷款
    side            VARCHAR NOT NULL, -- 'asset' | 'liability'
    name            VARCHAR NOT NULL,
    amount          FLOAT   NOT NULL,
    currency        VARCHAR NOT NULL DEFAULT 'CNY',
    note            VARCHAR,
    -- extra fields for loans / options (do not affect totals)
    price           FLOAT,
    quantity        FLOAT,
    start_date      VARCHAR,
    end_date        VARCHAR,
    interest_rate   FLOAT,
    monthly_payment FLOAT,
    create_time     DATETIME NOT NULL,
    update_time     DATETIME NOT NULL
);
-- COALESCE handles NULL account_id / sub_account_id (SQLite treats NULLs as distinct)
CREATE UNIQUE INDEX IF NOT EXISTS uq_balance_item
    ON balance_items (snapshot_id, side, COALESCE(account_id, -1), COALESCE(sub_account_id, -1), category);

-- ── dividend_history (yfinance dividend data per symbol) ──────────────────────
-- History is fetched once; ex_date / annual_rate refreshed every 24 h via ticker.info.
CREATE TABLE IF NOT EXISTS dividend_history (
    id            INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    symbol        VARCHAR  NOT NULL UNIQUE,
    ex_date       VARCHAR,           -- next upcoming ex-dividend date (YYYY-MM-DD)
    pay_date      VARCHAR,           -- next payment date
    annual_rate   FLOAT,             -- per-share annual dividend in local currency
    history_json  TEXT,              -- JSON: [{date: YYYY-MM-DD, amount: float}]
    fetched_at    VARCHAR,           -- ISO UTC datetime of last yfinance fetch
    create_time   DATETIME NOT NULL,
    update_time   DATETIME NOT NULL
);

-- ── price_history (daily close prices per symbol, cached from yfinance) ────────
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    symbol      VARCHAR  NOT NULL,
    date        VARCHAR  NOT NULL,  -- YYYY-MM-DD
    close       FLOAT    NOT NULL,
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_price_history_sym_date
    ON price_history (symbol, date);

-- ── benchmark_custom_schemes (per-account benchmark allocation definitions) ────
-- is_portfolio_snapshot=1 rows are auto-generated snapshots of actual holdings.
CREATE TABLE IF NOT EXISTS benchmark_custom_schemes (
    id                    INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id               BIGINT,
    account_id            INTEGER  NOT NULL,
    name                  VARCHAR  NOT NULL,
    allocations_json      TEXT     NOT NULL,  -- JSON: [{"symbol": str, "pct": float}]
    cash_pct              FLOAT    NOT NULL DEFAULT 0.0,
    enabled               INTEGER  NOT NULL DEFAULT 1,
    is_portfolio_snapshot INTEGER  NOT NULL DEFAULT 0,
    create_time           DATETIME NOT NULL,
    update_time           DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_benchmark_custom_schemes_acct_name
    ON benchmark_custom_schemes (account_id, name);

-- ── benchmark_results (computed XIRR results per account / scheme / date) ──────
-- bench_id = "__portfolio__" for the actual portfolio, or the scheme name.
CREATE TABLE IF NOT EXISTS benchmark_results (
    id                INTEGER  NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id           BIGINT,
    account_id        INTEGER  NOT NULL,
    bench_id          VARCHAR  NOT NULL,  -- "__portfolio__" or scheme name
    computed_date     VARCHAR  NOT NULL,  -- YYYY-MM-DD
    xirr              FLOAT,
    current_value_usd FLOAT,              -- terminal value in USD
    computed_at       DATETIME,           -- exact timestamp of last compute
    create_time       DATETIME NOT NULL,
    update_time       DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_benchmark_results_acct_bench_date
    ON benchmark_results (account_id, bench_id, computed_date);
