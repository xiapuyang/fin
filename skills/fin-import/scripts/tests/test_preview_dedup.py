import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from preview import dedup, NATURAL_KEYS


def test_dedup_alerts_skips_match():
    existing = [{"symbol": "AAPL", "condition": "price_gte", "value": 200.0}]
    incoming = [
        {"symbol": "AAPL", "condition": "price_gte", "value": 200.0, "name": "Apple"},
        {"symbol": "TSLA", "condition": "price_gte", "value": 150.0, "name": "Tesla"},
    ]
    new, skipped = dedup("alerts", incoming, existing)
    assert len(new) == 1 and new[0]["symbol"] == "TSLA"
    assert skipped == 1


def test_dedup_holdings_uses_account_code_snapshot():
    existing = [{"account": "IBKR", "code": "AAPL", "snapshot_name": "current"}]
    incoming = [
        {"account": "IBKR", "code": "AAPL", "snapshot_name": "current", "market": "US"},
        {"account": "IBKR", "code": "AAPL", "snapshot_name": "Q1", "market": "US"},
    ]
    new, skipped = dedup("holdings", incoming, existing)
    assert len(new) == 1 and skipped == 1


def test_dedup_empty_existing():
    new, skipped = dedup(
        "alerts", [{"symbol": "X", "condition": "price_gte", "value": 1}], []
    )
    assert len(new) == 1 and skipped == 0


def test_natural_keys_cover_all_domains():
    expected = {
        "alerts",
        "transactions",
        "holdings",
        "income",
        "ledger",
        "balance",
        "watchlist",
    }
    assert set(NATURAL_KEYS.keys()) == expected
