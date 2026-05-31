import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from detect_type import detect


def test_detect_alerts():
    assert detect("symbol,condition,value\nAAPL,price_gte,200") == "alerts"


def test_detect_transactions():
    assert (
        detect("date,code,side,shares,price\n2026-01-15,AAPL,buy,10,185")
        == "transactions"
    )


def test_detect_holdings():
    assert detect("code,market,shares,avg_cost\nAAPL,US,50,150") == "holdings"


def test_detect_ledger():
    assert (
        detect(
            "direction,name,date,amount,category\nexpense,Groceries,2026-01-15,120,0001"
        )
        == "ledger"
    )


def test_detect_balance():
    assert (
        detect("name,category,side,amount,currency\nChecking,cash,asset,15000,USD")
        == "balance"
    )


def test_detect_income():
    assert (
        detect("date,amount,currency,name,category\n2026-01-15,5000,USD,Salary,salary")
        == "income"
    )


def test_detect_watchlist():
    assert detect("symbol\nAAPL\nTSLA") == "watchlist"


def test_detect_ambiguous():
    assert detect("value\n100\n200") == "ambiguous"
