# Skills

fin 项目随附的 Claude Code skills，用于批量数据操作。每个子目录是一个独立可安装的 skill。

## 已内置的 Skills

- **fin-import** (`fin-import/`) — 批量导入数据到 fin，支持 7 种数据类型：提醒、交易记录、持仓、收支、账本、资产负债表条目、自选股。可处理真实银行/券商导出的混乱格式，通过 LLM 自动归一化。详见 `fin-import/SKILL.md`。
- **fin-accounts** (`fin-accounts/`) — 批量创建资产负债表账户（父账户 + 子账户），支持从文字描述或内置模板生成。详见 `fin-accounts/SKILL.md`。

## 安装

使用软链接（不要复制），这样在本仓库的改动立即生效，无需重新同步。

```bash
# 全局安装（所有项目、所有会话均可用）
ln -s "$(pwd)/skills/fin-import"   ~/.claude/skills/fin-import
ln -s "$(pwd)/skills/fin-accounts" ~/.claude/skills/fin-accounts

# 项目级安装（仅在本项目的 Claude 会话中可用）
mkdir -p .claude/skills
ln -s "$(pwd)/skills/fin-import"   .claude/skills/fin-import
ln -s "$(pwd)/skills/fin-accounts" .claude/skills/fin-accounts
```

安装后重启 Claude 会话，或执行 `/skills reload`。

## 开发

直接编辑 `skills/<name>/` 下的文件——软链接保证改动立即生效。
在当前 Claude 会话中执行 `/skills reload` 即可加载最新版本。
如果 backend schema 有变更，需要重新生成 JSON Schema 模板：

```bash
uv run python -m scripts.export_schemas
```

> `starter_accounts.json` 在两个 skills 的 `assets/` 目录中各有一份（共享词汇表），
> 修改时需同步更新两份。
