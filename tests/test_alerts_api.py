import json
import pytest
from unittest.mock import patch


# ── Health & Symbols ──────────────────────────────────────────────────────────


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_symbols_found(client, tmp_path, monkeypatch):
    symbols_file = tmp_path / "symbols.json"
    symbols_file.write_text(json.dumps([{"code": "AAPL", "name": "Apple"}]))
    import fin.routers.alerts as alerts_mod

    monkeypatch.setattr(alerts_mod, "SYMBOLS_PATH", symbols_file)
    r = client.get("/api/symbols")
    assert r.status_code == 200
    assert r.json()[0]["code"] == "AAPL"


def test_get_symbols_not_found(client, tmp_path, monkeypatch):
    import fin.routers.alerts as alerts_mod

    monkeypatch.setattr(alerts_mod, "SYMBOLS_PATH", tmp_path / "missing.json")
    r = client.get("/api/symbols")
    assert r.status_code == 404


# ── Quote ─────────────────────────────────────────────────────────────────────


def test_get_quote_success(client):
    # prev_close=100 → change_pct = (110-100)/100*100 = 10.0 exactly
    live = {"price": 110.0, "prev_close": 100.0, "currency": "USD"}
    with patch(
        "fin.services.providers.yfinance_provider.YFinanceProvider.fetch_live",
        return_value=live,
    ):
        r = client.get("/api/quote/AAPL")
    assert r.status_code == 200
    data = r.json()
    assert data["price"] == 110.0
    assert data["symbol"] == "AAPL"
    assert data["change_pct"] == pytest.approx(10.0)


def test_get_quote_missing_price(client):
    with patch(
        "fin.services.providers.yfinance_provider.YFinanceProvider.fetch_live",
        return_value={},
    ):
        r = client.get("/api/quote/AAPL")
    assert r.status_code == 503


def test_get_quote_fetch_error(client):
    # Providers swallow network exceptions and return {}.
    # Simulate that contract: QuoteService receives {} and returns None → 503.
    with patch(
        "fin.services.providers.yfinance_provider.YFinanceProvider.fetch_live",
        return_value={},
    ):
        r = client.get("/api/quote/AAPL")
    assert r.status_code == 503


# ── Alert CRUD ────────────────────────────────────────────────────────────────


def _alert_payload(**kwargs):
    base = {"symbol": "AAPL", "name": "Apple", "condition": "price_gte", "value": 200.0}
    return {**base, **kwargs}


def test_list_alerts_empty(client):
    r = client.get("/api/alerts")
    assert r.status_code == 200
    assert r.json() == []


def test_create_alert(client):
    r = client.post("/api/alerts", json=_alert_payload())
    assert r.status_code == 201
    data = r.json()
    assert data["code"] == "AAPL"
    assert data["name"] == "Apple"
    assert data["enabled"] is True
    assert isinstance(data["id"], int)


def test_create_alert_normalizes_symbol(client):
    r = client.post("/api/alerts", json=_alert_payload(symbol=".SPX", value=5000.0))
    assert r.status_code == 201
    assert r.json()["code"] == "^GSPC"


def test_create_duplicate_alert_returns_409(client):
    client.post("/api/alerts", json=_alert_payload())
    r = client.post("/api/alerts", json=_alert_payload())
    assert r.status_code == 409


def test_list_alerts_returns_created(client):
    client.post("/api/alerts", json=_alert_payload())
    r = client.get("/api/alerts")
    assert len(r.json()) == 1


def test_list_alerts_enabled_filter(client):
    r = client.post("/api/alerts", json=_alert_payload())
    alert_id = r.json()["id"]
    client.put(f"/api/alerts/{alert_id}", json={"enabled": False})
    r = client.get("/api/alerts?enabled=true")
    assert r.json() == []


def test_update_alert_name(client):
    r = client.post("/api/alerts", json=_alert_payload())
    alert_id = r.json()["id"]
    r2 = client.put(f"/api/alerts/{alert_id}", json={"name": "Apple Inc"})
    assert r2.status_code == 200
    assert r2.json()["name"] == "Apple Inc"


def test_update_alert_condition(client):
    r = client.post("/api/alerts", json=_alert_payload())
    alert_id = r.json()["id"]
    r2 = client.put(
        f"/api/alerts/{alert_id}", json={"condition": "price_lte", "value": 150.0}
    )
    assert r2.status_code == 200
    assert r2.json()["cond"] == "price_lte"


def test_update_alert_not_found(client):
    r = client.put("/api/alerts/999999", json={"name": "X"})
    assert r.status_code == 404


def test_update_alert_duplicate_condition_returns_409(client):
    client.post("/api/alerts", json=_alert_payload(name="A1"))
    r2 = client.post(
        "/api/alerts",
        json=_alert_payload(name="A2", condition="price_lte", value=150.0),
    )
    alert_id = r2.json()["id"]
    r = client.put(
        f"/api/alerts/{alert_id}", json={"condition": "price_gte", "value": 200.0}
    )
    assert r.status_code == 409


def test_delete_alert(client):
    r = client.post("/api/alerts", json=_alert_payload())
    alert_id = r.json()["id"]
    r2 = client.delete(f"/api/alerts/{alert_id}")
    assert r2.status_code == 204
    assert client.get("/api/alerts").json() == []


def test_reset_alert(client):
    r = client.post("/api/alerts", json=_alert_payload())
    alert_id = r.json()["id"]
    client.put(f"/api/alerts/{alert_id}", json={"enabled": False})
    r2 = client.post(f"/api/alerts/{alert_id}/reset")
    assert r2.status_code == 200
    assert r2.json()["enabled"] is True


def test_reset_alert_not_found(client):
    r = client.post("/api/alerts/999999/reset")
    assert r.status_code == 404


# ── History ───────────────────────────────────────────────────────────────────


def test_history_empty(client):
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_limit_param(client):
    r = client.get("/api/history?limit=10")
    assert r.status_code == 200


# ── Last Check ────────────────────────────────────────────────────────────────


def test_last_check_missing_file(client, tmp_path, monkeypatch):
    import fin.routers.settings as settings_mod

    monkeypatch.setattr(settings_mod, "LAST_CHECK_PATH", tmp_path / "missing.json")
    r = client.get("/api/last-check")
    assert r.status_code == 200
    assert r.json() == {"checked_at": None}


def test_last_check_present(client, tmp_path, monkeypatch):
    import fin.routers.settings as settings_mod

    p = tmp_path / "last_check.json"
    p.write_text('{"checked_at": "2026-05-04T10:00:00Z"}')
    monkeypatch.setattr(settings_mod, "LAST_CHECK_PATH", p)
    r = client.get("/api/last-check")
    assert r.status_code == 200
    assert r.json()["checked_at"] == "2026-05-04T10:00:00Z"


def test_last_check_malformed_file(client, tmp_path, monkeypatch):
    import fin.routers.settings as settings_mod

    p = tmp_path / "last_check.json"
    p.write_text("not json{{")
    monkeypatch.setattr(settings_mod, "LAST_CHECK_PATH", p)
    r = client.get("/api/last-check")
    assert r.status_code == 200
    assert r.json() == {"checked_at": None}
