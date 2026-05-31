def _ledger(**kw):
    base = {
        "direction": "expense",
        "name": "Groceries",
        "date": "2026-01-15",
        "amount": 120.0,
        "currency": "CAD",
        "category": "0001",
    }
    base.update(kw)
    return base


def test_bulk_create_ledger_success(client):
    r = client.post(
        "/api/ledger/bulk",
        json=[_ledger(), _ledger(name="Gas")],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}
    names = {i["name"] for i in client.get("/api/ledger").json()["items"]}
    assert names == {"Groceries", "Gas"}


def test_bulk_create_ledger_dedups(client):
    client.post("/api/ledger", json=_ledger())
    r = client.post(
        "/api/ledger/bulk",
        json=[_ledger(), _ledger(name="Gas")],
    )
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_ledger_validation_aborts(client):
    r = client.post(
        "/api/ledger/bulk",
        json=[_ledger(), {"direction": "expense"}],
    )
    assert r.status_code == 422
    assert client.get("/api/ledger").json()["items"] == []


def test_bulk_create_ledger_empty(client):
    r = client.post("/api/ledger/bulk", json=[])
    assert r.json() == {"created": 0, "skipped": 0, "errors": []}
