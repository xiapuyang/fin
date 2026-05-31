# Skills

Development source for Claude Code skills shipped with the fin project. Each subdirectory is one independently-installable skill.

## Skills shipped

- **fin-import** (`fin-import/`) — bulk-import data into the fin app across 7 domains: alerts, transactions, holdings, income, ledger, balance items, watchlist. See `fin-import/SKILL.md`.
- **fin-accounts** (`fin-accounts/`) — batch create balance accounts (parent + sub-accounts) from text or seed from the bundled template. See `fin-accounts/SKILL.md`.

## Install

Pick one location per skill:

```bash
# Global install (all projects, all sessions)
cp -r skills/fin-import   ~/.claude/skills/
cp -r skills/fin-accounts ~/.claude/skills/

# Project-local install (this project only)
mkdir -p .claude/skills
cp -r skills/fin-import   .claude/skills/
cp -r skills/fin-accounts .claude/skills/
```

After install, restart the Claude session or run `/skills reload`.

## Develop

Edit files under `skills/<name>/` directly. To re-test a change in a current
Claude session, re-copy the affected skill dir and run `/skills reload`. To
regenerate JSON Schema templates after backend schema changes:

```bash
uv run python -m scripts.export_schemas
```

`starter_accounts.json` is intentionally duplicated in both skills' `assets/`
(shared parsing vocabulary). Update both copies in lockstep.
