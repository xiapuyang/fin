def _holding_payload(**kw):
    base = {
        "code": "AAPL",
        "market": "US",
        "currency": "USD",
        "shares": 10,
        "avg_cost": 150.0,
        "account": "IBKR",
        "snapshot_name": "current",
    }
    base.update(kw)
    return base


def test_bulk_create_holdings_success(client):
    r = client.post(
        "/api/holdings/bulk",
        json=[_holding_payload(code="AAPL"), _holding_payload(code="TSLA")],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}
    assert {h["code"] for h in client.get("/api/holdings").json()} == {"AAPL", "TSLA"}


def test_bulk_create_holdings_dedups(client):
    client.post("/api/holdings", json=_holding_payload(code="AAPL"))
    r = client.post(
        "/api/holdings/bulk",
        json=[_holding_payload(code="AAPL"), _holding_payload(code="TSLA")],
    )
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_holdings_validation_aborts(client):
    r = client.post(
        "/api/holdings/bulk",
        json=[_holding_payload(code="AAPL"), {"code": "TSLA"}],
    )
    assert r.status_code == 422
    assert client.get("/api/holdings").json() == []


def test_bulk_create_holdings_empty(client):
    r = client.post("/api/holdings/bulk", json=[])
    assert r.json() == {"created": 0, "skipped": 0, "errors": []}
