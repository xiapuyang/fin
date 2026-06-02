# fin

个人或家庭财务管理工具。把家庭财务当成一家公司来经营 —— 通过三张财务报表追踪资金流向，回答一个核心问题：**什么时候可以达到 FIRE 退休目标？**

- **收入支出 (Income Statement)** — 工资 / 分红 / 利息 / 消费按类别分组，月度汇总。
- **资产负债 (Balance Sheet)** — 多账户、多币种快照管理，自动 FX 换算到净值。
- **现金流 (Cash Flow)** — 转入 / 转出 / 买入 / 卖出，组合成可对账的资金流动。

最终落到一个 FIRE 计算器：基于真实历史数据估算达到财务自由的时间点。

## 为什么用 fin

**把所有账户收敛到一张表**，是这个工具最核心的事情。市面上的工具要么只管港 A 股票，要么只管美股，要么只管记账 —— 资产分散在中港美三地的人最后只能开 N 个表 + 一个手动汇总 Excel。fin 把它们放进一个数据库一个 UI：

- **跨市场股票账户** — 中国 A 股、港股、美股、ETF、指数；自选股 watchlist 跨市场实时行情。
- **多币种实时换算** — 持仓 / 收支 / 净值都按账户原币种存储，CNY / USD / HKD / CAD 通过 yfinance 实时 FX 换算到统一币种汇总，汇率获取失败回退到常驻 fallback。
- **储蓄 / 理财 / 信用卡全覆盖** — 活期、定期、GIC、货币基金、现金管理、信用卡分期 —— 都是资产负债表上一个普通账户，统一快照、统一对账。
- **IRR 年化回报率** — 基于转入 / 转出现金流 + 当前持仓市值用 Newton-Raphson 解 XIRR，单账户和全账户都能算 MWRR，比"涨跌幅"更贴近真实回报率。
- **批量数据导入** — 一次性把券商导出的 CSV、银行流水、持仓列表灌进系统；带预览 / 去重 / 确认门，幂等可重跑。配套 Claude Code skill (`skills/fin-import`) 让 LLM 直接处理脏数据。
- **价格提醒** — 美股 / 港股 / A 股 / 指数的价格 + 涨跌幅条件提醒，cron 每 20 分钟检查，触发后发邮件。

## Features

- **Dashboard** — 净值、汇率、市场快照、watchlist 行情
- **Alerts** — 美股 / 港股 / A 股 / 指数价格条件提醒（cron 每 20 分钟检查，触发后邮件通知）
- **Holdings** — 持仓 + 交易记录 + 分红 / 利息 / 转账，已实现 / 未实现盈亏，**XIRR 年化回报率**
- **Ledger** — 收入支出记账，按类别月度汇总
- **Balance Sheet** — 账户层级（父/子）、多币种快照对比、复制上一期快照、自动 FX 换算到统一净值
- **FIRE Calculator** — 蒙特卡洛模拟 + 确定性 CAGR 反推 + 通胀调整

## Screenshots

> 以下截图均为演示数据，与任何真实账户无关。

| Dashboard | Alerts |
|---|---|
| ![Dashboard](assets/screenshots/dashboard.png) | ![Alerts](assets/screenshots/alerts.png) |

| Holdings | Ledger |
|---|---|
| ![Holdings](assets/screenshots/holdings.png) | ![Ledger](assets/screenshots/ledger.png) |

| Balance Sheet | FIRE |
|---|---|
| ![Balance](assets/screenshots/balance.png) | ![FIRE](assets/screenshots/fire.png) |

## Quickstart

### 前置：安装 uv

依赖 [`uv`](https://github.com/astral-sh/uv) 管理 Python 环境（替代 pip / venv / pipx，速度快一个数量级）。先确认本机已装：

```bash
uv --version    # 已装 → 跳过下一步
```

如果命令找不到，按平台二选一安装：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或者 Homebrew
brew install uv

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

装完重开 shell 让 `uv` 进 PATH，再 `uv --version` 验证。

### 启动

前端无构建步骤（React + Babel standalone 走 CDN），后端一条 `uv run` 起服务：

```bash
git clone <repo-url>
cd fin
uv sync                    # install Python deps
cp config/.env.example ~/.fin/data/.env  # 可选：填写 AgentMail 凭据
uv run python serve.py     # http://localhost:8888
```

打开浏览器访问 [http://localhost:8888](http://localhost:8888) 即可。首次访问会自动建库（`data/fin.db`）。

### Server scripts

也可以用仓库根目录的脚本以后台方式管理服务，PID 写到 `fin.pid`，日志输出到 `logs/fin.log`：

```bash
./run.sh        # 启动（后台），等待端口 8888 绑定成功
./stop.sh       # 优雅停止（SIGTERM → 等待 → 必要时 SIGKILL）
./restart.sh    # 先 stop 后 run
```

## Email Alerts (optional)

价格提醒可以在触发时发邮件。完整通路需要三件事：AgentMail 账号 + 环境变量 + cron。三件都不配也能跑 —— 提醒照常触发并写入 DB，只是不发邮件。

### 1. 申请 AgentMail

前往 [agentmail.to](https://agentmail.to) 注册，拿到：

- **API key**（格式 `am_xxx`）
- **Inbox id**（格式 `agent_xxx@agentmail.to`，作为发件邮箱）

AgentMail 是这个项目用的邮件发送服务。也可以自己改 `check_alerts.py` 的 `_send_email` 接其他 provider。

### 2. 填 `.env`

```env
AGENTMAIL_API_KEY=am_xxx
FIN_AGENTMAIL_INBOX=agent_xxx@agentmail.to
```

任一空 → 跳过发送（仍记 fire 到 DB）。

### 3. 注册 cron

`check_alerts.py` 是独立脚本，靠 cron 周期调用。推荐每 20 分钟一次：

```cron
# crontab -e
*/20 * * * * cd /path/to/fin && /path/to/uv run python check_alerts.py
```

### 4. UI 启用

TopBar 齿轮 → 应用设置 → 填**通知邮箱** + 打开**触发提醒通知** 开关 → 保存。这是收件地址，跟 .env 里的发件 inbox 是两回事。

### 5. 端到端验证

`verify_email.py` 一次性自检整条链路：`.env` 凭据、`settings.json` 收件人、SQLite DB、crontab 注册、发一封真模板的预览邮件（合成 2 条示例触发，让你看到红涨绿跌的最终样式）。

```bash
uv run python verify_email.py            # 全检 + 发预览邮件
uv run python verify_email.py --no-send  # 只检查，不发邮件
uv run python verify_email.py --to a@b.com  # 临时覆盖收件人
```

任何一步 FAIL → 退出码 1；crontab 缺失只 WARN（你可能用 launchd / systemd 调度）。

## Stack

- **Backend** — Python 3.11+, FastAPI, SQLAlchemy, SQLite, yfinance, AgentMail
- **Frontend** — React 18 + Babel standalone（无构建步骤）
- **Data** — `data/fin.db`（SQLite，启动时自动建库）

## License

[MIT](LICENSE)
