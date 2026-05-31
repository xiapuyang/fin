"""Pipeline integration tests for fin-import and fin-accounts skills.

What this tests
---------------
Runs the actual skill scripts (detect_type, parse_input, transform,
parse_accounts) against fixture inputs in `tests/fixtures/fin_skill_inputs/`.
Each test asserts the canonical rows + gaps + AskUserQuestion-equivalent
behavior the skill produces — without hitting any network or DB.

How AskUserQuestion gets "mocked"
---------------------------------
The Python scripts never call AskUserQuestion themselves — AUQ is driven by
Claude orchestration inside SKILL.md. The scripts expose pure functions with
kwargs (`default_account=`, `snapshot_id=`) representing "what the user would
have answered". Passing those kwargs == simulating the user's answer.

For full SKILL.md flow validation including the real AUQ dialog, drive the
skill manually in a Claude session — there's no automated path for that.
"""

import json
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "fin_skill_inputs"
SKILLS = Path(__file__).parent.parent / "skills"

# Make skill scripts importable
sys.path.insert(0, str(SKILLS / "fin-import" / "scripts"))
sys.path.insert(0, str(SKILLS / "fin-accounts" / "scripts"))

from detect_type import detect  # noqa: E402
from parse_accounts import parse_csv, parse_text  # noqa: E402
from parse_input import parse  # noqa: E402
from preview import dedup  # noqa: E402
from transform import TEMPLATES_DIR, transform  # noqa: E402


def _template(domain: str) -> dict:
    return json.loads((TEMPLATES_DIR / f"{domain}.json").read_text())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


# ── fin-import: detect_type ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("alerts_clean.csv", "alerts"),
        ("alerts_chinese.csv", "alerts"),
        ("transactions_ambig_date.csv", "transactions"),
        ("holdings_inject_account.csv", "holdings"),
        ("balance_chinese_vocab.csv", "balance"),
        ("watchlist_csv.csv", "watchlist"),
        ("ambiguous.csv", "ambiguous"),
        # Bare symbol list with no header context is intentionally ambiguous —
        # the skill is expected to AskUserQuestion in this case.
        ("watchlist_symbols.txt", "ambiguous"),
    ],
)
def test_detect_type_routes_inputs(fixture, expected):
    assert detect(_read(fixture)) == expected


# ── fin-import: parse → transform pipeline ────────────────────────────────────


def test_alerts_clean_pipeline():
    rows = parse(text=_read("alerts_clean.csv"), format="csv")
    result = transform(rows, _template("alerts"))
    assert result.gaps == []
    assert len(result.rows) == 3
    assert result.rows[0] == {
        "symbol": "NVDA",
        "name": "Nvidia",
        "condition": "price_gte",
        "value": 500.0,
    }


def test_alerts_chinese_aliases_map_to_canonical():
    rows = parse(text=_read("alerts_chinese.csv"), format="csv")
    result = transform(rows, _template("alerts"))
    assert result.gaps == []
    assert {r["symbol"] for r in result.rows} == {"NVDA", "0700.HK"}
    assert result.rows[0]["condition"] == "price_gte"


def test_alerts_missing_required_field_flags_gap():
    rows = parse(text=_read("alerts_missing.csv"), format="csv")
    result = transform(rows, _template("alerts"))
    missing = {g.field for g in result.gaps if g.kind == "missing_required"}
    assert "value" in missing


def test_alerts_unknown_column_flagged():
    rows = parse(text=_read("alerts_unknown_col.csv"), format="csv")
    result = transform(rows, _template("alerts"))
    unmapped = {g.field for g in result.gaps if g.kind == "unmapped_column"}
    assert "trigger_at" in unmapped


def test_transactions_ambiguous_date_flagged():
    rows = parse(text=_read("transactions_ambig_date.csv"), format="csv")
    result = transform(rows, _template("transactions"))
    ambig = [g for g in result.gaps if g.kind == "ambiguous_date"]
    assert len(ambig) == 2  # both rows have ambiguous dates


def test_holdings_default_account_injected_via_auq_simulation():
    """Simulates: user answered 'IBKR' to AskUserQuestion('which account?')."""
    rows = parse(text=_read("holdings_inject_account.csv"), format="csv")
    result = transform(rows, _template("holdings"), default_account="IBKR")
    assert all(r["account"] == "IBKR" for r in result.rows)
    assert len(result.rows) == 3


def test_holdings_without_default_account_kwarg_has_no_account():
    """Without the AUQ-simulated kwarg, account stays empty."""
    rows = parse(text=_read("holdings_inject_account.csv"), format="csv")
    result = transform(rows, _template("holdings"))
    assert all("account" not in r for r in result.rows)


def test_income_name_alias_maps_to_source():
    """Plan-corrected aliases: 'name' column maps to canonical 'source' field."""
    rows = parse(text=_read("income_name_alias.csv"), format="csv")
    result = transform(rows, _template("income"))
    assert result.gaps == []
    assert result.rows[0]["source"] == "Vanguard ETF"
    assert "name" not in result.rows[0]


def test_balance_chinese_vocab_passes_through():
    rows = parse(text=_read("balance_chinese_vocab.csv"), format="csv")
    result = transform(rows, _template("balance"), snapshot_id=42)
    assert result.gaps == []
    assert result.rows[0]["snapshot_id"] == 42
    assert result.rows[0]["category"] == "现金"
    assert result.rows[2]["side"] == "liability"


def test_watchlist_txt_one_per_line():
    rows = parse(text=_read("watchlist_symbols.txt"), format="txt")
    # txt parser names the single column "value" — needs to be remapped to "symbol"
    # in real flow. Here we just confirm parsing works.
    assert len(rows) == 4
    assert rows[0]["value"] == "AAPL"
    assert rows[3]["value"] == "0700.HK"


# ── fin-import: preview dedup ────────────────────────────────────────────────


def test_preview_dedup_against_existing_alerts():
    incoming = [
        {"symbol": "NVDA", "name": "Nvidia", "condition": "price_gte", "value": 500.0},
        {"symbol": "META", "name": "Meta", "condition": "price_lte", "value": 400.0},
    ]
    existing = [{"symbol": "NVDA", "condition": "price_gte", "value": 500.0}]
    new, skipped = dedup("alerts", incoming, existing)
    assert skipped == 1
    assert len(new) == 1 and new[0]["symbol"] == "META"


# ── fin-accounts ──────────────────────────────────────────────────────────────


def test_accts_plain_roots_only():
    out = parse_text(_read("accts_plain.txt"))
    assert out == [{"name": "IB"}, {"name": "WealthSimple"}, {"name": "招商银行"}]


def test_accts_slash_separator():
    out = parse_text(_read("accts_slash.txt"))
    # Parent listed before its children; parent dedups across multiple subs
    assert {r["name"] for r in out if "parent_name" not in r} == {"IB", "招商银行"}
    children = [r for r in out if "parent_name" in r]
    assert {(c["name"], c["parent_name"]) for c in children} == {
        ("股票账户", "IB"),
        ("现金", "IB"),
        ("人民币", "招商银行"),
        ("美元", "招商银行"),
    }


def test_accts_arrow_separator():
    out = parse_text(_read("accts_arrow.txt"))
    assert {r["name"] for r in out if "parent_name" not in r} == {
        "WealthSimple",
        "招商银行",
    }
    assert {"Chequing", "Savings", "港币"} == {
        r["name"] for r in out if "parent_name" in r
    }


def test_accts_csv_with_blank_sub():
    out = parse_csv(_read("accts.csv"))
    # WealthSimple row has blank sub → just the root
    parents_with_blank = [r for r in out if r.get("name") == "WealthSimple"]
    assert parents_with_blank == [{"name": "WealthSimple"}]


def test_accts_comments_and_dedup():
    out = parse_text(_read("accts_comments.txt"))
    parents = [r for r in out if "parent_name" not in r]
    # 招商银行 only appears once even though 2 sub-lines reference it
    assert sum(1 for r in parents if r["name"] == "招商银行") == 1
    assert sum(1 for r in parents if r["name"] == "IB") == 1
