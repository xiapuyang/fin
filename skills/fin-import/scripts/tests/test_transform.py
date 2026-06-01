import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from transform import TEMPLATES_DIR, transform


def _t(domain):
    return json.loads((TEMPLATES_DIR / f"{domain}.json").read_text())


def test_aliased_columns_map():
    t = _t("alerts")
    out = transform(
        [{"代码": "AAPL", "name": "Apple", "条件": "price_gte", "值": "200"}], t
    )
    assert out.rows == [
        {"symbol": "AAPL", "name": "Apple", "condition": "price_gte", "value": 200.0}
    ]
    assert out.gaps == []


def test_default_account_stamped():
    t = _t("transactions")
    out = transform(
        [
            {
                "date": "2026-01-15",
                "code": "AAPL",
                "side": "buy",
                "shares": "10",
                "price": "185",
                "currency": "USD",
            }
        ],
        t,
        default_account="IBKR",
    )
    assert out.rows[0]["account"] == "IBKR"


def test_snapshot_id_stamped():
    t = _t("balance")
    out = transform(
        [
            {
                "name": "Checking",
                "category": "cash",
                "side": "asset",
                "amount": "15000",
                "currency": "USD",
            }
        ],
        t,
        snapshot_id=42,
    )
    assert out.rows[0]["snapshot_id"] == 42


def test_missing_required_flagged():
    t = _t("alerts")
    out = transform([{"symbol": "AAPL"}], t)
    missing = {g.field for g in out.gaps if g.kind == "missing_required"}
    assert {"name", "condition", "value"} <= missing


def test_unmapped_column_flagged():
    t = _t("alerts")
    out = transform(
        [
            {
                "symbol": "AAPL",
                "weird": "x",
                "name": "A",
                "condition": "price_gte",
                "value": "1",
            }
        ],
        t,
    )
    assert any(g.kind == "unmapped_column" and g.field == "weird" for g in out.gaps)


def test_ambiguous_date_flagged():
    t = _t("transactions")
    out = transform(
        [
            {
                "date": "02/03/2026",
                "code": "AAPL",
                "side": "buy",
                "shares": "10",
                "price": "185",
                "currency": "USD",
            }
        ],
        t,
    )
    assert any(g.kind == "ambiguous_date" for g in out.gaps)
