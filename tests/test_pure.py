import locale
from types import SimpleNamespace

from fin.routers.alerts import _normalize_symbol
from fin.services.alert_checker import check_condition as _check_condition
from fin.alert_email import build_summary_email
from fin.settings import _detect_os_locale


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


# ── build_summary_email ──────────────────────────────────────────────────────


def _make_alert(name="Apple", symbol="AAPL", condition="price_gte", value=200.0):
    return SimpleNamespace(name=name, symbol=symbol, condition=condition, value=value)


def test_single_alert_subject_contains_name_and_symbol():
    alert = _make_alert()
    subject, _, _ = build_summary_email([(alert, 201.0, 0.5)])
    assert "Apple" in subject
    assert "AAPL" in subject


def test_multi_alert_subject_contains_count():
    alert = _make_alert()
    subject, _, _ = build_summary_email([(alert, 201.0, 0.5), (alert, 201.0, 0.5)])
    assert "2" in subject


def test_email_body_contains_price():
    alert = _make_alert()
    _, html, text = build_summary_email([(alert, 201.5, 0.5)])
    assert "201.50" in html
    assert "201.50" in text


def test_email_body_contains_change():
    alert = _make_alert()
    _, html, text = build_summary_email([(alert, 201.5, 1.23)])
    assert "+1.23%" in html
    assert "+1.23%" in text


def test_email_zh_subject_html_and_text_localized(monkeypatch):
    from fin import alert_email as _ae

    monkeypatch.setattr(_ae._settings, "load", lambda: {"language": "zh"})
    alert = _make_alert(name="苹果", symbol="AAPL")
    subject, html, text = build_summary_email([(alert, 201.5, 1.23)])
    assert "提醒触发" in subject
    assert "📊 股票提醒触发" in html
    assert "名称" in html and "代码" in html
    # Plain-text lead-in must be Chinese, not "Triggered N alert(s)"
    assert text.startswith("触发 ")
    assert "Triggered" not in text
    assert "以上提醒已自动禁用" in text


def test_email_en_text_lead_in_english(monkeypatch):
    from fin import alert_email as _ae

    monkeypatch.setattr(_ae._settings, "load", lambda: {"language": "en"})
    alert = _make_alert()
    _, _, text = build_summary_email([(alert, 201.5, 1.23)])
    assert text.startswith("Triggered ")
    assert "alert(s):" in text


# ── _detect_os_locale ────────────────────────────────────────────────────────


def test_detect_os_locale_returns_supported_value():
    assert _detect_os_locale() in {"en", "zh"}


def test_detect_os_locale_chinese_from_lang_env(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: (None, None))
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert _detect_os_locale() == "zh"


def test_detect_os_locale_chinese_from_getlocale(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: ("zh_TW", "UTF-8"))
    assert _detect_os_locale() == "zh"


def test_detect_os_locale_falls_back_to_en_for_other_locales(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: ("ja_JP", "UTF-8"))
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    assert _detect_os_locale() == "en"


def test_detect_os_locale_ignores_C_posix(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: (None, None))
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.setenv("LANG", "C")
    assert _detect_os_locale() == "en"


def test_email_crlf_in_alert_name_stripped(monkeypatch):
    """Alert name containing CRLF must not break MIME structure in text body."""
    from fin import alert_email as _ae

    monkeypatch.setattr(_ae._settings, "load", lambda: {"language": "en"})
    alert = _make_alert(name="Bad\r\nHeader", symbol="X")
    _, _, text = build_summary_email([(alert, 1.0, 0.0)])
    assert "\r" not in text
    # Newlines exist as legitimate row separators, but the alert name's embedded
    # newline must have been collapsed to a space.
    assert "Bad Header" in text or "Bad  Header" in text
