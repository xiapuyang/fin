# fin

个人财务仪表盘 — 跨市场持仓、资产负债、记账、FIRE 计算，本地运行，数据不出本机。

| Dashboard | Holdings |
|---|---|
| ![Dashboard](assets/screenshots/dashboard.png) | ![Holdings](assets/screenshots/holdings.png) |

## 安装（桌面应用）

### macOS

1. 下载 `Fin-vX.X.X-arm64.dmg`（Apple Silicon）或 `Fin-vX.X.X-intel.dmg`（Intel）
2. 打开 DMG，将 **Fin.app** 拖入 Applications
3. 首次启动前在终端运行：

```bash
xattr -cr /Applications/Fin.app
```

4. 双击启动，菜单栏右上角出现 Fin 图标，浏览器自动打开

> `xattr -cr` 是因为 App 未经 Apple 公证，macOS 会阻止未知来源的应用运行。这是本地工具的正常步骤。

### Windows

1. 下载 `Fin-Setup-vX.X.X.exe`
2. 运行安装程序（需要 Windows 10 或更高版本）
3. 从开始菜单启动 Fin

## 功能

- **Dashboard** — 净值总览、持仓市值、市场状态、watchlist 行情
- **Alerts** — 股票价格 / 涨跌幅条件提醒，触发后可邮件通知
- **Holdings** — 持仓 + 交易记录，XIRR 年化回报率
- **Ledger** — 收入支出记账，按类别月度汇总
- **Balance Sheet** — 多账户多币种资产负债快照
- **FIRE** — 财务自由计算器，蒙特卡洛模拟 + 确定性推演

数据保存在本机 `~/.fin/data/`，卸载应用不会自动删除。

---

## 开发

### 环境

依赖 [`uv`](https://github.com/astral-sh/uv)：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv
```

### 启动

```bash
git clone <repo-url>
cd fin
uv sync
uv run python serve.py     # http://localhost:8888
```

脚本方式（后台运行，日志写到 `~/.fin/logs/fin.log`）：

```bash
./run.sh      # 启动，等待端口绑定后自动打开浏览器
./stop.sh     # 停止
./restart.sh  # 重启
```

Dev 模式（独立数据库，端口 18888）：

```bash
./run.sh --dev    # http://localhost:18888
```

### 打包

```bash
./build.sh                   # Mac DMG，当前架构
./build.sh --target mac-arm64
./build.sh --target mac-intel
./build.sh --target windows  # 仅 Windows 环境
```

依赖：`pyinstaller`（已在 uv 环境中）、`create-dmg`（macOS：`brew install create-dmg`）、Inno Setup（Windows）。

### 邮件提醒（可选）

价格提醒触发时可以发邮件。不配置也能正常使用，提醒照常记录到 DB，只是不发邮件。

1. 在 [agentmail.to](https://agentmail.to) 注册，获取 API Key 和 Inbox ID
2. 在应用设置（齿轮图标）→ AgentMail 中填写，或写入 `~/.fin/data/.env`：

```env
AGENTMAIL_API_KEY=am_xxx
FIN_AGENTMAIL_INBOX=agent_xxx@agentmail.to
```

3. 在应用设置中填写**通知邮箱**并打开通知开关
4. 注册 cron（server 模式）：

```bash
# crontab -e
*/20 * * * * cd /path/to/fin && /path/to/uv run python check_alerts.py
```

验证整条链路：

```bash
uv run python verify_email.py            # 全检 + 发预览邮件
uv run python verify_email.py --no-send  # 只检查
```

## Stack

Python 3.11+, FastAPI, SQLAlchemy, SQLite, yfinance / akshare · React 18 + Babel standalone（无构建步骤）
