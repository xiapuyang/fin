# Skills

Development source for Claude Code skills shipped with the fin project. Each subdirectory is one independently-installable skill.

## Skills shipped

- **fin-import** (`fin-import/`) — bulk-import data into the fin app across 7 domains: alerts, transactions, holdings, income, ledger, balance items, watchlist. See `fin-import/SKILL.md`.
- **fin-accounts** (`fin-accounts/`) — batch create balance accounts (parent + sub-accounts) from text or seed from the bundled template. See `fin-accounts/SKILL.md`.

## Install

Symlink (not copy) so edits in this repo take effect immediately — no re-sync needed.

```bash
# Global install (all projects, all sessions)
ln -s "$(pwd)/skills/fin-import"   ~/.claude/skills/fin-import
ln -s "$(pwd)/skills/fin-accounts" ~/.claude/skills/fin-accounts

# Project-local install (this project only)
mkdir -p .claude/skills
ln -s "$(pwd)/skills/fin-import"   .claude/skills/fin-import
ln -s "$(pwd)/skills/fin-accounts" .claude/skills/fin-accounts
```

After install, restart the Claude session or run `/skills reload`.

## Develop

Edit files under `skills/<name>/` directly — symlinks mean changes are live.
Run `/skills reload` in the current Claude session to pick them up. To
regenerate JSON Schema templates after backend schema changes:

```bash
uv run python -m scripts.export_schemas
```

`starter_accounts.json` is intentionally duplicated in both skills' `assets/`
(shared parsing vocabulary). Update both copies in lockstep.
