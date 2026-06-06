from unittest.mock import patch

import fin.settings as settings_mod


def test_get_settings_returns_defaults(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert "notify_email" in data
    assert "notify_enabled" in data


def test_put_settings_updates_email(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"notify_email": "test@example.com"})
    assert r.status_code == 200
    assert r.json()["notify_email"] == "test@example.com"


def test_put_settings_updates_notify_enabled(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"notify_enabled": False})
    assert r.status_code == 200
    assert r.json()["notify_enabled"] is False


def test_put_settings_persists(client, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", path)
    client.put("/api/settings", json={"notify_email": "persist@example.com"})
    r = client.get("/api/settings")
    assert r.json()["notify_email"] == "persist@example.com"


def test_put_settings_persists_display_name(client, tmp_path, monkeypatch):
    """Regression: display_name was dropped by SettingsPayload before this test existed."""
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"display_name": "Alice"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Alice"
    assert client.get("/api/settings").json()["display_name"] == "Alice"


def test_put_settings_language_accepted(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"language": "zh"})
    assert r.status_code == 200
    assert r.json()["language"] == "zh"
    assert client.get("/api/settings").json()["language"] == "zh"


def test_put_settings_language_rejects_invalid(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"language": "fr"})
    assert r.status_code == 422


def test_put_settings_enabled_markets_accepted(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"enabled_markets": ["us", "hk"]})
    assert r.status_code == 200
    assert r.json()["enabled_markets"] == ["us", "hk"]


def test_put_settings_enabled_markets_rejects_unknown(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"enabled_markets": ["us", "xx"]})
    assert r.status_code == 422


def test_get_credentials_never_returns_full_api_key(client, monkeypatch):
    """Regression: GET must not leak the full key. DNS-rebinding + CORS bug
    would let a cross-origin page exfiltrate the key if we did."""
    monkeypatch.setenv("AGENTMAIL_API_KEY", "sk-supersecretpayload-1234")
    monkeypatch.setenv("FIN_AGENTMAIL_INBOX", "alerts@inbox.agentmail.to")
    r = client.get("/api/settings/credentials")
    assert r.status_code == 200
    data = r.json()
    assert "agentmail_api_key" not in data
    assert data["agentmail_api_key_set"] is True
    assert data["agentmail_api_key_hint"] == "1234"
    # Full key value must not appear anywhere in the response.
    assert "sk-supersecretpayload-1234" not in r.text
    # The inbox is not a secret — full value is fine.
    assert data["agentmail_inbox"] == "alerts@inbox.agentmail.to"


def test_get_credentials_no_hint_for_short_keys(client, monkeypatch):
    """Short keys (<8 chars) reveal too much in 4-char hint; omit it."""
    monkeypatch.setenv("AGENTMAIL_API_KEY", "short")
    r = client.get("/api/settings/credentials")
    data = r.json()
    assert data["agentmail_api_key_set"] is True
    assert data["agentmail_api_key_hint"] == ""


def test_get_credentials_no_key_set(client, monkeypatch):
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    monkeypatch.delenv("FIN_AGENTMAIL_INBOX", raising=False)
    r = client.get("/api/settings/credentials")
    data = r.json()
    assert data["agentmail_api_key_set"] is False
    assert data["agentmail_api_key_hint"] == ""
    assert data["agentmail_inbox"] == ""


def test_get_fx_returns_rates_via_quote_service(client):
    fake_rates = {"USD": 7.24, "HKD": 0.93, "CAD": 5.30, "CNY": 1.0}
    with patch("fin.routers.settings.QuoteService") as mock_qs:
        mock_qs.return_value.get_fx.return_value = fake_rates
        with patch("fin.routers.settings.build_default_providers", return_value=[]):
            r = client.get("/api/fx")
    assert r.status_code == 200
    data = r.json()
    assert data["USD"] == 7.24
    assert data["CNY"] == 1.0


def test_get_fx_falls_back_on_error(client):
    with patch("fin.routers.settings.QuoteService") as mock_qs:
        mock_qs.return_value.get_fx.side_effect = Exception("provider down")
        with patch("fin.routers.settings.build_default_providers", return_value=[]):
            r = client.get("/api/fx")
    assert r.status_code == 200
    data = r.json()
    assert data["USD"] == 7.24
    assert data["HKD"] == 0.93
    assert data["CAD"] == 5.30
    assert data["CNY"] == 1.0
    assert "EUR" not in data


# ── settings.py internals ─────────────────────────────────────────────────────


def test_load_returns_defaults_on_corrupt_json(tmp_path, monkeypatch):
    import fin.settings as s

    path = tmp_path / "settings.json"
    path.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(s, "SETTINGS_PATH", path)
    result = s.load()
    assert "language" in result  # defaults returned


def test_detect_os_locale_falls_back_to_env_when_getlocale_raises(monkeypatch):
    import locale
    import fin.settings as s

    monkeypatch.setattr(
        locale, "getlocale", lambda: (_ for _ in ()).throw(Exception("no locale"))
    )
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    result = s._detect_os_locale()
    assert result == "zh"


def test_detect_os_locale_win32_ctypes_chinese(monkeypatch):
    import sys
    import fin.settings as s

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.delenv("LANG", raising=False)

    import unittest.mock as m

    fake_ctypes = m.MagicMock()
    fake_ctypes.windll.kernel32.GetUserDefaultUILanguage.return_value = 0x0804  # zh-CN
    with m.patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        with m.patch("locale.getlocale", return_value=(None, None)):
            result = s._detect_os_locale()
    assert result == "zh"
