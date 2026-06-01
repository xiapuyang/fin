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
