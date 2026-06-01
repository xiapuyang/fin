---
name: fin-import
description: Bulk-import data into the fin app (a local personal-finance dashboard at http://localhost:8888) across 7 domains — alerts, transactions, holdings, income, ledger, balance sheet items, watchlist. Auto-detects type from input, asks upfront for account / snapshot date / format ambiguities, shows a confirmation gate before any write, and is idempotent (skips duplicates server-side and previews them client-side). Triggers on phrases like "import to fin", "导入到 fin", "fin 导入", "bulk add transactions to fin", "把这些持仓加进 fin", or any time the user provides tabular data (CSV or pasted text) plus intent to write it to the fin app. Use fin-accounts (not this skill) when the user wants to set up balance accounts WITHOUT importing data.
---

# fin-import

Bulk importer for the fin app. Accepts pasted text, `.txt`, or `.csv`. (xlsx not supported — convert to CSV first.)

## When to use

Trigger when the user wants to populate the fin app (running at `http://localhost:8888`) with one of:

- **alerts** — price/change conditions on symbols
- **transactions** — buy/sell history (single account per import)
- **holdings** — current positions snapshot (single account per import)
- **income** — salary, dividends, interest
- **ledger** — expense/income entries (everyday spending)
- **balance** — snapshot rows for the balance sheet (asks for snapshot date)
- **watchlist** — symbols to track without alerts

## Runtime flow

Run scripts under `scripts/` via `python scripts/<name>.py`. Scripts that make HTTP calls (`preview.py`, `post_bulk.py`) require `requests`: run them as `uv run --with requests python scripts/<name>.py`. The skill orchestrates them in this order:

0. **Preflight: announce target URL** — run `python scripts/_fin_url.py` once at the start. It prints `[fin] → <url>  (<reason>)` to stderr so the user sees which fin instance (dev 18888 / prod 8888 / explicit) will be touched before any prompts or writes.
1. **Detect type** — `detect_type.py < input`. If `ambiguous`, AskUserQuestion to pick.
2. **Preflight (per type):**
   - `transactions` / `holdings`: AskUserQuestion for the target `account`. If the account doesn't exist (`GET /api/accounts`), ask for `currency`, optional `balance_account_id` (showing current balance accounts), optional `cutoff_date`. Then `POST /api/accounts` to create.
   - `balance`: resolve the snapshot. Steps:
     a. AskUserQuestion for snapshot date (default today, YYYY-MM-DD).
     b. `snapshot_resolver.py find --date YYYY-MM-DD` → prints the matching snapshot dict, or `null`.
     c. If found → AskUserQuestion: "Snapshot for `<date>` exists (label='X', N items). Append more items? [Yes / Pick different date / Cancel]". Yes → use that `id`.
     d. If not found → AskUserQuestion: "No snapshot for `<date>`. Create new snapshot? [label?]". On confirm → `snapshot_resolver.py create --date YYYY-MM-DD --label TEXT` → prints the created record.
     The resolved `snapshot_id` is then passed to `transform.py --snapshot-id`.
   - `income`: if no `account` column in input AND multiple accounts exist, ask which to attribute.
3. **Parse input** — `parse_input.py <file_or_-> --format <csv|txt>` returns `list[dict]`. `.txt` is one-value-per-line input; each line becomes `{"symbol": line}` by default. Realistically only useful for **watchlist** (other domains need ≥4 fields per row). Override key with `--txt-key NAME` if a future single-field domain needs it.
4. **Transform** — `transform.py --type <domain> --rows <json> [--default-account NAME] [--snapshot-id N]` returns canonical schema list + a `gaps` list (unmapped columns, missing required fields, ambiguous dates). For each gap kind, ask the user once per gap (not per row):
   - Unmapped column → "Map column X to which field? [list canonical fields + 'skip']"
   - Missing required field for all rows → "All rows missing `currency`, set default for this import?"
   - Missing required for some rows → "Skip these N rows or fill in manually?"
   - Ambiguous date → "Format MM/DD or DD/MM?"
5. **Account name resolution (balance only)** — for rows carrying `account` / `sub_account` name strings (passed through transform via `extra_fields`):
   a. `balance_account_resolver.py list` → array of `{id, parent_id, name, parent_name}` from the **current env's API**.
   b. For each unique `(account, sub_account)` pair:
      - Exact-match `account` to a parent (where `parent_id is None`); then exact-match `sub_account` to a child whose `parent_id` equals that parent's id. Both hit → assign `account_id` (parent id) + `sub_account_id` (child id). (The schema field naming is unfortunate: `account_id` actually points to the PARENT row, `sub_account_id` to the child. This matches `BalanceItemCreate`.)
      - Only the parent matches (sub doesn't) → AskUserQuestion derived **at runtime** by the LLM inspecting the existing subs under that parent + the row's full context (`currency`, item `name`, `category`). Use semantic judgment, not a fixed similarity formula — same approach as ledger category resolution (step 5b/c). E.g. row `currency=CNY, sub_account=储蓄` under a 招商银行 parent whose subs are 人民币/美元/港币/朝朝宝/朝朝赢 — LLM proposes "人民币 (default for CNY cash at this parent)" as a candidate alongside "create new sub 储蓄". Always include "Create new sub under parent", "Attach to parent only (no sub)", and "Skip rows" as options. Put reasoning in each option's `description`.
      - Neither matches → AskUserQuestion: "Account `<X>/<Y>` doesn't exist. Create parent `<X>` + sub `<Y>`? / Create parent only / Pick from existing list / Skip rows". When proposing existing candidates, the LLM ranks the tree by semantic closeness (e.g. user typed "招商" → suggest "招商银行" / "招商信用卡"). No fixed similarity formula — just inspect the list.
   c. On "create" decisions, call `balance_account_resolver.py create --name NAME [--parent-id N]`; capture returned IDs.
   d. Strip `account` and `sub_account` from canonical rows; inject `account_id` / `sub_account_id` integers. Then preview + post.
5b. **Category resolution (ledger only)** — for any row whose `category` value is a name (not an ID like `"0002"`):
   a. `category_resolver.py list` → array of `{id, direction, name}` from the **current env's API** (never read `data/` or `data-dev/` JSON directly — those may belong to a different instance).
   b. Exact `(direction, name)` match → swap `category` to the ID, continue.
   c. No exact match → for each unmapped name, AskUserQuestion with options derived **at runtime** by inspecting the existing list against the unmapped name. Use semantic judgment, not a fixed similarity formula: e.g. `饮食` → suggest mapping to `餐饮`; `Uber` / `打车` → suggest `交通`; `Amazon` / `星巴克` → suggest `购物`. Always include "Create new custom category" and "Skip these N rows" as options. Pre-articulate: state the reasoning briefly in the option `description` so the user can audit ("`饮食` and `餐饮` both mean food/eating").
   d. User picks "Create new" → `category_resolver.py create --direction <expense|income> --name <NAME>` → returns the new record with its ID; use that ID.
   e. User picks "Skip rows" → drop those rows from the canonical list before preview.
6. **Preview + dedup** — `preview.py --type <domain> --rows <canonical.json>` fetches existing data via `GET /api/<domain>`, performs client-side dedup using the documented natural keys, prints:
   ```
   ── fin import preview: <domain> ──
   Will create: N
   Already exists (skip): M
   Sample (first 3 new rows):
     [0] { ... }
     [1] { ... }
     [2] { ... }
   ```
7. **Hard confirmation gate** — AskUserQuestion: "Create N <domain> rows? [Yes / No]". Do not proceed without explicit Yes.
8. **POST** — `post_bulk.py --type <domain> --rows <json>` calls the appropriate bulk endpoint (FIN_API_URL env, default `http://localhost:8888`).
9. **Report** — print the final summary block (see below).

## Endpoint mapping

| Domain | Endpoint |
|---|---|
| alerts | `POST /api/alerts/bulk` |
| transactions | `POST /api/transactions/bulk` |
| holdings | `POST /api/holdings/bulk` |
| income | `POST /api/income/bulk` |
| ledger | `POST /api/ledger/bulk` |
| balance | `POST /api/balance/items/bulk` |
| watchlist | `POST /api/watchlist/bulk` |
| balance_accounts | `POST /api/balance/accounts/bulk` |
| accounts (single) | `POST /api/accounts` |

## Required-field contract

Before any POST, the skill must have these fields populated for every row.
Anything missing → ask once per import (per-import default) or per row only as last resort.

| Domain | Required (from schema) | Skill-derived |
|---|---|---|
| alerts | symbol, name, condition, value | — |
| transactions | date, code, side, shares, price, currency | account (upfront) |
| holdings | code, market, currency, shares, avg_cost | account, snapshot_name (upfront, defaults) |
| income | date, amount, currency, name, category | account (upfront if multiple exist) |
| ledger | direction, name, date, amount, currency, category | — |
| balance | name, category, side, amount, currency | snapshot_id (upfront), account_id/sub_account_id (resolved) |
| watchlist | symbol | — |

## Decision contract (when to ask)

- **Type ambiguous** → AskUserQuestion with 7 domains
- **Account doesn't exist (tx/holdings)** → AskUserQuestion 1: "Create account 'X' with currency Y, link to balance account Z? [Yes / Modify / Cancel]"
- **Snapshot date (balance)** → AskUserQuestion: "Snapshot date for this import? [today / YYYY-MM-DD]"
- **Field missing for all rows** → AskUserQuestion with default value choices
- **Date format ambiguous** (`02/03/2026`) → AskUserQuestion: MM/DD or DD/MM
- **Unknown column** → AskUserQuestion: "Column 'X' — map to which field?"
- **Before any POST** → AskUserQuestion: "Create N rows? [Yes / No]"

## Environment isolation

The skill targets exactly one fin instance per run — dev (`http://127.0.0.1:18888`, marker `~/.fin-dev`) or prod (`http://127.0.0.1:8888`). `_fin_url.py` is the only place that decides which. **Never `cat` files under `data/` or `data-dev/` to "check" what categories / accounts / snapshots / settings exist** — that bypasses the env switch and silently reads the wrong instance. Always go through the API (`GET /api/categories`, `GET /api/accounts`, `GET /api/balance/snapshots`, `GET /api/settings`, etc.). If an endpoint is missing for what you need, add one rather than reading the JSON file. Tooling like `category_resolver.py list` and `snapshot_resolver.py find` exist for exactly this reason.

## Error handling

- **fin not running** → "fin is not running at $FIN_API_URL — start with `uv run python serve.py` and retry"
- **422 from bulk endpoint** → whole batch rejected; print detail; write full payload to `/tmp/fin-import-error-<ts>.json`; stop
- **5xx** → stop; do not retry
- **Hook gate (any AskUserQuestion answer "No")** → exit cleanly, no write
- **REFUSED: dev+prod ports both reachable, ~/.fin-dev missing** — `_fin_url.resolve_base()` refuses to pick a port when both 8888 and 18888 are reachable and the dev marker is absent. Create `~/.fin-dev` (touch it) on this machine if it's a dev box; otherwise stop one of the servers.

## Output format

```
✓ fin: <domain>
  Created: N
  Skipped (duplicates): M
  Errors:  E
  <if E > 0> Details: /tmp/fin-import-error-<ts>.json
  <if writes happened> Refresh the fin app at http://localhost:8888 to see new data.
```

## Templates

`templates/` holds 7 JSON files generated from fin's Pydantic schemas by
`scripts/export_schemas.py` in the fin project. Each file has:
- `schema` — JSON Schema for the canonical payload
- `aliases` — column-header synonyms (e.g. `"date": ["date", "日期", "trade_date"]`)
- `examples` — 1+ valid payloads for few-shot transformation

Regenerate after backend schema changes: `uv run python -m scripts.export_schemas`.

## Starter accounts (parsing vocabulary)

`assets/starter_accounts.json` ships a small, privacy-pruned account hierarchy
(11 parents covering broker / bank / credit card / wallet / crypto / cash /
fixed asset / mortgage / debt / options / social insurance). It's the skill's
parsing reference: when a user pastes "招商美元 5000" or "IB 股票", the skill
consults this file to map account references to parent/sub.

Heavily anonymized: family-member accounts removed entirely, country-specific
accounts removed (no Canadian / HK / SG banks), each account type keeps only
one canonical example, property/employer names abstracted. Use as vocabulary
hints, not authoritative — real users will add their own accounts via
fin-accounts skill or the UI.
