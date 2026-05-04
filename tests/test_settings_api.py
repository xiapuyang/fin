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
