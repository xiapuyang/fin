from types import SimpleNamespace

from fin.routers.alerts import _normalize_symbol
from check_alerts import _build_summary_email, _check_condition


# ── _normalize_symbol ─────────────────────────────────────────────────────────


def test_normalize_spx():
    assert _normalize_symbol(".SPX") == "^GSPC"


def test_normalize_ndx():
    assert _normalize_symbol(".NDX") == "^NDX"


def test_normalize_dji():
    assert _normalize_symbol(".DJI") == "^DJI"


def test_normalize_unknown_passthrough():
    assert _normalize_symbol("AAPL") == "AAPL"


def test_normalize_case_insensitive():
    assert _normalize_symbol(".spx") == "^GSPC"


# ── _check_condition ──────────────────────────────────────────────────────────


def test_price_gte_triggers():
    assert _check_condition("price_gte", 100.0, 100.0, 0.0) is True


def test_price_gte_below():
    assert _check_condition("price_gte", 100.0, 99.9, 0.0) is False


def test_price_lte_triggers():
    assert _check_condition("price_lte", 100.0, 100.0, 0.0) is True


def test_price_lte_above():
    assert _check_condition("price_lte", 100.0, 100.1, 0.0) is False


def test_change_gte_triggers():
    assert _check_condition("change_gte", 2.0, 0.0, 2.5) is True


def test_change_gte_below():
    assert _check_condition("change_gte", 2.0, 0.0, 1.9) is False


def test_change_lte_triggers():
    assert _check_condition("change_lte", -2.0, 0.0, -2.5) is True


def test_change_lte_above():
    assert _check_condition("change_lte", -2.0, 0.0, -1.9) is False


def test_unknown_condition_returns_false():
    assert _check_condition("unknown_cond", 100.0, 100.0, 0.0) is False


# ── _build_summary_email ──────────────────────────────────────────────────────


def _make_alert(name="Apple", symbol="AAPL", condition="price_gte", value=200.0):
    return SimpleNamespace(name=name, symbol=symbol, condition=condition, value=value)


def test_single_alert_subject_contains_name_and_symbol():
    alert = _make_alert()
    subject, _, _ = _build_summary_email([(alert, 201.0, 0.5)])
    assert "Apple" in subject
    assert "AAPL" in subject


def test_multi_alert_subject_contains_count():
    alert = _make_alert()
    subject, _, _ = _build_summary_email([(alert, 201.0, 0.5), (alert, 201.0, 0.5)])
    assert "2" in subject


def test_email_body_contains_price():
    alert = _make_alert()
    _, html, text = _build_summary_email([(alert, 201.5, 0.5)])
    assert "201.50" in html
    assert "201.50" in text


def test_email_body_contains_change():
    alert = _make_alert()
    _, html, text = _build_summary_email([(alert, 201.5, 1.23)])
    assert "+1.23%" in html
    assert "+1.23%" in text
