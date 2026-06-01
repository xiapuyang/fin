import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parse_input import parse


def test_parse_csv_text():
    rows = parse(text="symbol,value\nAAPL,200\nTSLA,150", format="csv")
    assert rows == [
        {"symbol": "AAPL", "value": "200"},
        {"symbol": "TSLA", "value": "150"},
    ]


def test_parse_csv_file(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("symbol,value\nAAPL,200\n")
    assert parse(path=str(p), format="csv") == [{"symbol": "AAPL", "value": "200"}]


def test_parse_txt_one_per_line():
    assert parse(text="AAPL\nTSLA", format="txt") == [
        {"value": "AAPL"},
        {"value": "TSLA"},
    ]


def test_parse_strips_and_skips_blanks():
    rows = parse(text="symbol,value\n  AAPL ,  200  \n\n , \nTSLA,150", format="csv")
    assert rows == [
        {"symbol": "AAPL", "value": "200"},
        {"symbol": "TSLA", "value": "150"},
    ]
