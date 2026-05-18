# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the API server (http://localhost:8899)
uv run python serve.py

# Run the alert checker manually (also used as a cron job)
uv run python check_alerts.py

# Install/sync dependencies
uv sync
```

No build step for the frontend — JSX is transpiled in-browser by Babel standalone.

## Architecture

**fin** is a personal finance dashboard with a FastAPI backend and a no-build React frontend. The server serves the frontend as static files from `frontend/`, so a single process handles everything.

### Backend (`fin/`)

```
fin/
  api.py          # App factory: registers routers, mounts frontend/, global exception handler
  config.py       # All paths and constants (DB_PATH, SYMBOLS_PATH, API_PORT, etc.)
  database.py     # SQLAlchemy engine + SessionLocal + init_db()
  context.py      # ContextVar for request_id (used by logging middleware)
  models/         # SQLAlchemy ORM models (AlertModel, AlertFireModel)
  schemas/        # Pydantic request/response schemas
  repositories/   # Repository pattern: base.py defines abstract interfaces,
                  # alert_sqlite.py + alert_fire_sqlite.py are the SQLite implementations
  routers/        # FastAPI route handlers (alerts.py is the only router so far)
```

**Alert lifecycle**: `enabled=True` → condition met → `check_alerts.py` disables alert, writes `AlertFireModel` row, sends email → user resets → `enabled=True` again.

**Alert conditions**: `price_gte`, `price_lte`, `change_gte`, `change_lte`. Symbol `.SPX` / `.NDX` / `.DJI` are normalized to yfinance format in `_normalize_symbol()`.

### Frontend (`frontend/`)

No bundler — React 18 and Babel standalone are loaded from CDN. All `.jsx` files in `src/` are included as `<script type="text/babel">` tags in `index.html` and share a single global scope.

```
src/
  app.jsx       # Root: Sidebar, TopBar, client-side routing (NAV array)
  atoms.jsx     # Shared UI primitives (Button, Card, Badge, etc.)
  icons.jsx     # SVG icon registry
  charts.jsx    # Recharts-style sparklines / chart primitives
  data.jsx      # API calls (fetchAlerts, createAlert, deleteAlert, etc.)
  dashboard.jsx # Overview / summary screen
  alerts.jsx    # Alert CRUD UI
  holdings.jsx  # Portfolio tracking (local-only, no backend yet)
  ledger.jsx    # Transaction ledger (local-only)
  balance.jsx   # Balance sheet (local-only)
  fire.jsx      # FIRE retirement calculator (local-only)
```

Routing is a simple `useState` string — no React Router.

### Documented Solutions (`docs/solutions/`)

Past bugs and fixes organized by category (`logic-errors/`, `ui-bugs/`, etc.) with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when debugging or refactoring in areas that may have prior history.

### Alert notifications (`check_alerts.py`)

Standalone cron script. Reads enabled alerts from the DB, fetches live prices via yfinance, fires matching alerts (records `AlertFireModel`, disables the alert, sends Gmail email). Email is sent via AgentMail. Requires `AGENTMAIL_API_KEY` env var and `notify_email` in `data/settings.json`.

## Common operations

### Account models — which is which

Two distinct account tables exist; pick the right one:

- `accounts` (`fin/models/account.py`) — flat list tied to **holdings / transactions** (broker / wallet accounts). Has `currency`, `cutoff_date`, `symbol_markets`, and `balance_account_id` / `balance_sub_account_id` pointers into the balance hierarchy.
- `balance_accounts` (`fin/models/balance_account.py`) — self-referencing **parent/child hierarchy** for the balance sheet. No `currency` column (currency lives on `balance_items` per snapshot).

When the user says "add account" without context, they usually mean the **balance sheet hierarchy** (`balance_accounts`).

### Add balance accounts (parent + sub) via DB

Use the repository directly — fastest, no server required. The frontend reads from `/api/balance/accounts` on next page load.

```python
uv run python -c "
from fin.database import SessionLocal
from fin.repositories.balance_account_sqlite import BalanceAccountSQLiteRepository
from fin.schemas.balance_account import BalanceAccountCreate
from fin.models.user import MOCK_USER_ID

db = SessionLocal()
repo = BalanceAccountSQLiteRepository(db)

# parent → list of sub-account names
PLAN = {
    'WealthSimple': ['现金'],
    'Simplii':      ['现金'],
}
existing = {a.name for a in repo.get_all(MOCK_USER_ID) if a.parent_id is None}
for parent_name, subs in PLAN.items():
    if parent_name in existing:
        print(f'skip: {parent_name}'); continue
    p = repo.create(BalanceAccountCreate(name=parent_name), MOCK_USER_ID)
    for sub in subs:
        repo.create(BalanceAccountCreate(name=sub, parent_id=p.id), MOCK_USER_ID)
    print(f'+ {p.name} ({len(subs)} subs)')
"
```

Naming conventions in the existing hierarchy (mixed — pick what matches the parent's style):

- **Currency labels**: `人民币`, `加元`, `美元`, `港币` — common for bank accounts holding multiple currencies (招商银行, 汇丰银行).
- **Product types**: `Checking`, `Savings`, `GIC`, `股票账户`, `信用卡分期消费` — used when the bank/broker offers distinct product lines.
- **Generic**: `现金`, `零钱` — used for single-purpose wallets.

### Add a brokerage / wallet account (`accounts` table)

Use the holdings router's `POST /api/accounts` endpoint (or `AccountSQLiteRepository` directly). Required: `name`. Common: `currency` (defaults to `CNY`), `note`, `balance_account_id` to link this broker into the balance hierarchy.

## Color convention

The UI uses **Chinese market convention**: red (`--up`) = price rising, green (`--down`) = price falling. This is intentional and opposite to Western convention — do not change it.

## Key design constraints

- SQLite DB lives at `data/fin.db`. The `data/` and `logs/` directories are created automatically at import time in `config.py`.
- All queries eager-load related models via `selectinload` to avoid N+1 issues.
- The frontend modules not yet backed by an API (holdings, ledger, balance, fire) are client-side only.

# Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
