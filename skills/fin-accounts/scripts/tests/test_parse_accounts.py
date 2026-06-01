import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parse_accounts import parse_text, parse_csv


def test_parse_text_plain_root():
    assert parse_text("IB\n汇丰银行") == [
        {"name": "IB"},
        {"name": "汇丰银行"},
    ]


def test_parse_text_slash_separator():
    assert parse_text("IB/股票账户\nIB/现金") == [
        {"name": "IB"},
        {"name": "股票账户", "parent_name": "IB"},
        {"name": "现金", "parent_name": "IB"},
    ]


def test_parse_text_arrow_separator():
    assert parse_text("汇丰银行 > 港币") == [
        {"name": "汇丰银行"},
        {"name": "港币", "parent_name": "汇丰银行"},
    ]


def test_parse_text_dedups_parent():
    """Multiple subs under same parent should only create the parent once."""
    result = parse_text("IB/股票账户\nIB/现金")
    parents = [r for r in result if "parent_name" not in r]
    assert parents == [{"name": "IB"}]


def test_parse_text_skips_blanks_and_comments():
    text = "\nIB\n# comment\n  \n汇丰银行"
    assert parse_text(text) == [{"name": "IB"}, {"name": "汇丰银行"}]


def test_parse_csv():
    text = "parent,sub\nIB,股票账户\nIB,现金\n汇丰银行,"
    assert parse_csv(text) == [
        {"name": "IB"},
        {"name": "股票账户", "parent_name": "IB"},
        {"name": "现金", "parent_name": "IB"},
        {"name": "汇丰银行"},
    ]
