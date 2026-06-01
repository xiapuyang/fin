---
name: fin-accounts
description: Batch create balance accounts (parent + sub-accounts) in the fin app. Two modes — (1) parse account names from user input (text/CSV: each line a "Parent" or "Parent/Sub"); (2) seed from the bundled starter_accounts.json template covering ~30 common broker/bank/wallet/card hierarchies (anonymized real reference). Always shows a confirmation gate before creating. Triggers on phrases like "set up fin accounts", "在 fin 里建账户", "fin 建一批账户", "create balance accounts", "use the starter accounts template", "init fin accounts". Use fin-import (not this skill) when the user has data to import — fin-import will inline-create missing accounts on its own.
---

# fin-accounts

Batch creator for fin's balance account hierarchy. Two entry modes: parse from user input OR seed from the bundled template.

## When to use

- Empty / first-time setup of the balance sheet's account tree
- User has a list of account names (text or CSV) to bulk-create
- User wants to apply the bundled starter template wholesale

If the user is importing data (not just setting up accounts), use **fin-import** instead — it handles missing-account creation inline.

## Runtime flow

0. **Preflight: announce target URL** — run `python scripts/_fin_url.py` once at the start. It prints `[fin] → <url>  (<reason>)` to stderr so the user sees which fin instance (dev 18899 / prod 8899 / explicit) will be touched before any prompts or writes.
1. **Mode detection** — AskUserQuestion if not obvious:
   - "Parse from your input" — user has text/CSV listing accounts
   - "Apply starter template" — use `assets/starter_accounts.json` (11 parents, minimal starter)
2. **Parse (mode 1)** — `parse_accounts.py <input>` returns `list[{name, parent_name?}]`. Format examples:
   - `汇丰银行` → parent account
   - `汇丰银行/人民币` → sub-account `人民币` under parent `汇丰银行` (slash form)
   - `汇丰银行,港币` → sub-account `港币` under parent `汇丰银行` (CSV form, parent in col 1, sub in col 2)
3. **Load (mode 2)** — read `assets/starter_accounts.json` directly.
4. **Diff against existing** — run `uv run --with requests python scripts/list_accounts.py` (handles dev/prod routing via `~/.fin-dev`), parse the JSON output, filter input rows by `(name, parent_name)` already present, report how many are new.
5. **Hard confirmation gate** — AskUserQuestion: "Create N accounts (M parent accounts, K sub-accounts)? [Yes / Show full list / Cancel]"
6. **POST** — `uv run --with requests python scripts/setup_accounts.py --rows <json>` → `POST /api/balance/accounts/bulk`.
7. **Report**:
   ```
   ✓ fin-accounts
     Created: N
     Skipped (already exist): M
     <if any> Errors: E — see /tmp/fin-accounts-error-<ts>.json
   ```

## Endpoint

`POST /api/balance/accounts/bulk` with payload `list[{name, parent_name?}]`. Server pre-filters duplicates by `(user_id, name, parent_id)`; unknown `parent_name` aborts the whole batch with 400.

## Starter template

`assets/starter_accounts.json` is the same file shipped with fin-import (parsing vocabulary there; seed source here). **11 parent accounts** picked as canonical type examples:

- **Broker**: IB
- **Bank**: 招商银行 (人民币/美元/港币/朝朝宝/朝朝赢/美元理财)
- **Credit card**: 招商信用卡
- **Wallet**: 微信 (零钱)
- **Crypto**: Kraken (虚拟货币账户)
- **Cash**: 现金 (人民币)
- **Fixed asset**: 固定资产 (汽车 / 自住房)
- **Mortgage**: 房贷 (自住房)
- **Debt**: 外债 (借出)
- **Options**: 期权 (雇主期权)
- **Social insurance**: 社保 (公积金 / 养老金 / 医保)

Country-specific accounts (CA / HK / SG banks), duplicate-type accounts, family-member accounts, and property/employer-specific names have all been pruned. Structure is real and useful as a seed; users will extend with their own accounts via this skill or the UI.

## Error handling

- **fin not running** → "fin is not running at $FIN_API_URL — start with `uv run python serve.py` and retry"
- **400 from bulk endpoint (unknown parent)** → print the missing parent names, suggest re-running with parents listed first
- **5xx** → stop; do not retry
- **Hook gate "No"** → exit cleanly, no write
