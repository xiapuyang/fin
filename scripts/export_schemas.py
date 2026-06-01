"""Export Pydantic create-schemas as JSON Schema templates for the fin skill.

Run: ``uv run python -m scripts.export_schemas [output_dir]``
Default output: ``<project>/skills/fin-import/templates/``

Each template file contains three keys:

- ``schema``   — JSON Schema generated from the Pydantic ``*Create`` model
- ``aliases``  — column-header synonyms for tolerant column mapping
- ``examples`` — at least one valid payload, used as a few-shot hint
"""

import json
import sys
from pathlib import Path

from fin.schemas.alert import AlertCreate
from fin.schemas.balance_item import BalanceItemCreate
from fin.schemas.holding import HoldingCreate
from fin.schemas.income import IncomeCreate
from fin.schemas.ledger import LedgerCreate
from fin.schemas.transaction import TransactionCreate
from fin.schemas.watchlist import WatchlistAdd

DOMAINS = [
    "alerts",
    "transactions",
    "holdings",
    "income",
    "ledger",
    "balance",
    "watchlist",
]

_SCHEMA_BY_DOMAIN = {
    "alerts": AlertCreate,
    "transactions": TransactionCreate,
    "holdings": HoldingCreate,
    "income": IncomeCreate,
    "ledger": LedgerCreate,
    "balance": BalanceItemCreate,
    "watchlist": WatchlistAdd,
}

_ALIASES = {
    "alerts": {
        "symbol": ["symbol", "代码", "code", "ticker"],
        "name": ["name", "名称"],
        "condition": ["condition", "条件", "type"],
        "value": ["value", "值", "price", "threshold"],
    },
    "transactions": {
        "date": ["date", "日期", "trade_date", "成交日期"],
        "code": ["code", "代码", "symbol", "ticker"],
        "side": ["side", "方向", "buy_sell"],
        "shares": ["shares", "数量", "qty", "quantity"],
        "price": ["price", "价格", "成交价"],
        "currency": ["currency", "币种", "ccy"],
    },
    "holdings": {
        "code": ["code", "代码", "symbol", "ticker"],
        "market": ["market", "市场", "exchange"],
        "shares": ["shares", "数量", "持仓"],
        "avg_cost": ["avg_cost", "成本", "cost"],
        "account": ["account", "账户", "broker"],
        "snapshot_name": ["snapshot_name", "snapshot", "快照"],
    },
    "income": {
        "date": ["date", "日期", "入账日"],
        "source": ["source", "name", "项目", "来源", "from"],
        "category": ["category", "分类", "type"],
        "amount": ["amount", "金额", "value"],
        "currency": ["currency", "币种", "ccy"],
    },
    "ledger": {
        "direction": ["direction", "方向", "type"],
        "name": ["name", "项目", "描述"],
        "date": ["date", "日期"],
        "amount": ["amount", "金额"],
        "currency": ["currency", "币种"],
        "category": ["category", "分类"],
    },
    "balance": {
        "snapshot_id": ["snapshot_id", "快照id", "snapshot"],
        "name": ["name", "项目", "账户"],
        "category": ["category", "分类"],
        "side": ["side", "类型", "asset_liability"],
        "amount": ["amount", "金额", "balance"],
        "currency": ["currency", "币种"],
    },
    "watchlist": {
        "symbol": ["symbol", "代码", "ticker"],
        "name": ["name", "名称"],
    },
}

_EXAMPLES = {
    "alerts": [
        {"symbol": "AAPL", "name": "Apple", "condition": "price_gte", "value": 200.0},
    ],
    "transactions": [
        {
            "date": "2026-01-15",
            "code": "AAPL",
            "side": "buy",
            "shares": 10,
            "price": 185.5,
            "currency": "USD",
            "account": "IBKR",
        },
    ],
    "holdings": [
        {
            "code": "AAPL",
            "market": "US",
            "currency": "USD",
            "shares": 50,
            "avg_cost": 150.0,
            "account": "IBKR",
            "snapshot_name": "current",
        },
    ],
    "income": [
        {
            "date": "2026-01-15",
            "source": "Vanguard ETF",
            "category": "dividend",
            "amount": 250.0,
            "currency": "USD",
        },
    ],
    "ledger": [
        {
            "direction": "expense",
            "name": "Groceries",
            "date": "2026-01-15",
            "amount": 120.0,
            "currency": "CAD",
            "category": "0001",
        },
    ],
    "balance": [
        {
            "snapshot_id": 1,
            "name": "活期账户",
            "category": "现金",
            "side": "asset",
            "amount": 15000.0,
            "currency": "CNY",
        },
    ],
    "watchlist": [{"symbol": "AAPL", "name": "Apple"}],
}

DEFAULT_OUTPUT = Path(__file__).parent.parent / "skills/fin-import/templates"


def build_template(domain: str) -> dict:
    """Build a single template dict for ``domain``.

    Args:
        domain: One of the keys in :data:`DOMAINS`.

    Returns:
        Dict with ``schema`` (JSON Schema), ``aliases`` (column synonyms),
        and ``examples`` (valid payloads).

    Raises:
        KeyError: If ``domain`` is not registered.
    """
    if domain not in _SCHEMA_BY_DOMAIN:
        raise KeyError(f"unknown domain: {domain}")
    return {
        "schema": _SCHEMA_BY_DOMAIN[domain].model_json_schema(),
        "aliases": _ALIASES[domain],
        "examples": _EXAMPLES[domain],
    }


def export_all(output_dir: Path) -> None:
    """Write one ``<domain>.json`` per domain into ``output_dir``.

    Args:
        output_dir: Destination directory (created if missing).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for domain in DOMAINS:
        path = output_dir / f"{domain}.json"
        path.write_text(
            json.dumps(build_template(domain), indent=2, ensure_ascii=False) + "\n"
        )


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    export_all(out)
    print(f"Wrote {len(DOMAINS)} templates to {out}")
