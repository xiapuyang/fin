"""Tests for rebalance, symbol-overrides, config, and credentials endpoints."""

import json
from unittest.mock import patch

import fin.routers.settings as settings_router
import fin.settings as settings_store


# ── GET /api/config ────────────────────────────────────────────────────────────


def test_get_config_returns_currencies(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "currencies" in data
    assert "CNY" in data["currencies"]


def test_put_settings_enabled_markets_null_accepted(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.put("/api/settings", json={"enabled_markets": None})
    assert r.status_code == 200


# ── GET /api/rebalance/defaults ────────────────────────────────────────────────


def test_get_rebalance_defaults_returns_list(client):
    fake = [{"id": "classic_60_40", "name": "60/40", "buckets": []}]
    with patch.object(settings_router, "APP_CONFIG", {"rebalance_defaults": fake}):
        r = client.get("/api/rebalance/defaults")
    assert r.status_code == 200
    assert r.json() == fake


def test_get_rebalance_defaults_empty_when_missing(client):
    with patch.object(settings_router, "APP_CONFIG", {}):
        r = client.get("/api/rebalance/defaults")
    assert r.status_code == 200
    assert r.json() == []


# ── GET /api/rebalance/categories ─────────────────────────────────────────────


def test_get_rebalance_categories_returns_list(client):
    fake = [{"id": "equity_us", "label_en": "US Stocks"}]
    with patch.object(settings_router, "APP_CONFIG", {"rebalance_categories": fake}):
        r = client.get("/api/rebalance/categories")
    assert r.status_code == 200
    assert r.json() == fake


def test_get_rebalance_categories_empty_when_missing(client):
    with patch.object(settings_router, "APP_CONFIG", {}):
        r = client.get("/api/rebalance/categories")
    assert r.status_code == 200
    assert r.json() == []


# ── GET /api/rebalance ─────────────────────────────────────────────────────────


def test_get_rebalance_returns_v3_when_present(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    v3 = {
        "active_id": "classic_60_40",
        "configs": [{"id": "classic_60_40", "buckets": []}],
    }
    client.put("/api/rebalance", json=v3)
    r = client.get("/api/rebalance")
    assert r.status_code == 200
    assert r.json()["active_id"] == "classic_60_40"


def test_get_rebalance_falls_back_to_v1(client, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", path)
    v1 = {"presetId": "personal", "buckets": [], "trigger": 5}
    path.write_text(json.dumps({"rebalance": v1}), encoding="utf-8")
    r = client.get("/api/rebalance")
    assert r.status_code == 200
    assert r.json()["presetId"] == "personal"


def test_get_rebalance_returns_empty_when_no_config(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    r = client.get("/api/rebalance")
    assert r.status_code == 200
    assert r.json() == {}


# ── PUT /api/rebalance ─────────────────────────────────────────────────────────


def test_put_rebalance_stores_v3_config(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    v3 = {
        "active_id": "personal",
        "configs": [{"id": "personal", "buckets": [], "trigger": 5}],
    }
    r = client.put("/api/rebalance", json=v3)
    assert r.status_code == 200
    assert r.json()["active_id"] == "personal"


def test_put_rebalance_persists_and_readable(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    v3 = {"active_id": "classic_60_40", "configs": []}
    client.put("/api/rebalance", json=v3)
    r = client.get("/api/rebalance")
    assert r.json()["active_id"] == "classic_60_40"


def test_put_rebalance_does_not_touch_legacy_key(client, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", path)
    path.write_text(
        json.dumps({"rebalance": {"presetId": "personal"}}), encoding="utf-8"
    )
    client.put("/api/rebalance", json={"active_id": "personal", "configs": []})
    saved = json.loads(path.read_text())
    assert saved.get("rebalance") == {"presetId": "personal"}
    assert "rebalance_v3" in saved


# ── GET /api/rebalance/symbol-overrides ───────────────────────────────────────


def test_get_symbol_overrides_returns_file_contents(client, tmp_path, monkeypatch):
    path = tmp_path / "symbol_overrides.json"
    path.write_text(json.dumps({"510310.SS": "etf_global"}), encoding="utf-8")
    monkeypatch.setattr(settings_router, "SYMBOL_OVERRIDES_PATH", path)
    r = client.get("/api/rebalance/symbol-overrides")
    assert r.status_code == 200
    assert r.json() == {"510310.SS": "etf_global"}


def test_get_symbol_overrides_returns_empty_when_file_missing(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        settings_router, "SYMBOL_OVERRIDES_PATH", tmp_path / "missing.json"
    )
    r = client.get("/api/rebalance/symbol-overrides")
    assert r.status_code == 200
    assert r.json() == {}


def test_get_symbol_overrides_returns_empty_on_read_error(
    client, tmp_path, monkeypatch
):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(settings_router, "SYMBOL_OVERRIDES_PATH", path)
    r = client.get("/api/rebalance/symbol-overrides")
    assert r.status_code == 200
    assert r.json() == {}


# ── PUT /api/rebalance/symbol-overrides ───────────────────────────────────────


def test_put_symbol_overrides_writes_file(client, tmp_path, monkeypatch):
    path = tmp_path / "symbol_overrides.json"
    monkeypatch.setattr(settings_router, "SYMBOL_OVERRIDES_PATH", path)
    payload = {"510310.SS": "etf_global", "159892.SZ": "equity_cn"}
    r = client.put("/api/rebalance/symbol-overrides", json=payload)
    assert r.status_code == 200
    assert r.json() == payload
    assert json.loads(path.read_text()) == payload


def test_put_symbol_overrides_rejects_non_dict(client, tmp_path, monkeypatch):
    path = tmp_path / "symbol_overrides.json"
    monkeypatch.setattr(settings_router, "SYMBOL_OVERRIDES_PATH", path)
    r = client.put("/api/rebalance/symbol-overrides", json=["not", "a", "dict"])
    assert r.status_code == 422


def test_put_symbol_overrides_rejects_null(client, tmp_path, monkeypatch):
    path = tmp_path / "symbol_overrides.json"
    monkeypatch.setattr(settings_router, "SYMBOL_OVERRIDES_PATH", path)
    r = client.put("/api/rebalance/symbol-overrides", json=None)
    assert r.status_code == 422


def test_put_symbol_overrides_propagates_write_error(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from fin.api import app

    path = tmp_path / "readonly" / "symbol_overrides.json"
    monkeypatch.setattr(settings_router, "SYMBOL_OVERRIDES_PATH", path)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.put("/api/rebalance/symbol-overrides", json={"A": "b"})
    assert r.status_code == 500


# ── PUT /api/settings/credentials ─────────────────────────────────────────────


def test_put_credentials_saves_api_key(client, tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(settings_router, "ENV_PATH", env_path)
    with patch("fin.routers.settings.set_key") as mock_set_key:
        r = client.put(
            "/api/settings/credentials", json={"agentmail_api_key": "sk-test-key"}
        )
    assert r.status_code == 200
    assert r.json()["saved"] is True
    mock_set_key.assert_called_once_with(
        str(env_path), "AGENTMAIL_API_KEY", "sk-test-key"
    )


def test_put_credentials_saves_inbox(client, tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(settings_router, "ENV_PATH", env_path)
    with patch("fin.routers.settings.set_key") as mock_set_key:
        r = client.put(
            "/api/settings/credentials",
            json={"agentmail_inbox": "alerts@inbox.example.com"},
        )
    assert r.status_code == 200
    mock_set_key.assert_called_once_with(
        str(env_path), "FIN_AGENTMAIL_INBOX", "alerts@inbox.example.com"
    )


def test_put_credentials_updates_environ(client, tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(settings_router, "ENV_PATH", env_path)
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    with patch("fin.routers.settings.set_key"):
        client.put("/api/settings/credentials", json={"agentmail_api_key": "sk-live"})
    import os

    assert os.environ.get("AGENTMAIL_API_KEY") == "sk-live"


def test_put_credentials_skips_none_fields(client, tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(settings_router, "ENV_PATH", env_path)
    with patch("fin.routers.settings.set_key") as mock_set_key:
        r = client.put("/api/settings/credentials", json={})
    assert r.status_code == 200
    mock_set_key.assert_not_called()
