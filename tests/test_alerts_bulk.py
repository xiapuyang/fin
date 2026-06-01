from tests.test_alerts_api import _alert_payload


def test_bulk_create_alerts_success(client):
    r = client.post(
        "/api/alerts/bulk",
        json=[_alert_payload(symbol="AAPL"), _alert_payload(symbol="TSLA")],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}
    assert {a["code"] for a in client.get("/api/alerts").json()} == {"AAPL", "TSLA"}


def test_bulk_create_alerts_skips_existing(client):
    client.post("/api/alerts", json=_alert_payload(symbol="AAPL"))
    r = client.post(
        "/api/alerts/bulk",
        json=[_alert_payload(symbol="AAPL"), _alert_payload(symbol="TSLA")],
    )
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_alerts_skips_within_input(client):
    r = client.post(
        "/api/alerts/bulk",
        json=[_alert_payload(symbol="AAPL"), _alert_payload(symbol="AAPL")],
    )
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_alerts_validation_aborts(client):
    r = client.post(
        "/api/alerts/bulk",
        json=[_alert_payload(symbol="AAPL"), {"symbol": "TSLA"}],
    )
    assert r.status_code == 422
    assert client.get("/api/alerts").json() == []


def test_bulk_create_alerts_empty(client):
    r = client.post("/api/alerts/bulk", json=[])
    assert r.json() == {"created": 0, "skipped": 0, "errors": []}
