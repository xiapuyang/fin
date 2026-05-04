import json
from unittest.mock import MagicMock, patch


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
    mock_info = MagicMock()
    mock_info.last_price = 150.0
    mock_info.previous_close = 148.0
    mock_info.currency = "USD"

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.fast_info = mock_info
        r = client.get("/api/quote/AAPL")

    assert r.status_code == 200
    data = r.json()
    assert data["price"] == 150.0
    assert data["symbol"] == "AAPL"


def test_get_quote_missing_price(client):
    mock_info = MagicMock()
    mock_info.last_price = None
    mock_info.previous_close = None

    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.fast_info = mock_info
        r = client.get("/api/quote/AAPL")

    assert r.status_code == 503


def test_get_quote_fetch_error(client):
    with patch("yfinance.Ticker", side_effect=RuntimeError("network error")):
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
    assert "id" in data


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
    r = client.put("/api/alerts/nonexistent-id", json={"name": "X"})
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
    r = client.post("/api/alerts/nonexistent-id/reset")
    assert r.status_code == 404


# ── History ───────────────────────────────────────────────────────────────────


def test_history_empty(client):
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_limit_param(client):
    r = client.get("/api/history?limit=10")
    assert r.status_code == 200
