def _txn(**kw):
    base = {
        "date": "2026-01-15",
        "code": "AAPL",
        "side": "buy",
        "shares": 10,
        "price": 185.0,
        "currency": "USD",
        "account": "IBKR",
    }
    base.update(kw)
    return base


def test_bulk_create_transactions_success(client):
    r = client.post("/api/transactions/bulk", json=[_txn(), _txn(code="TSLA")])
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}


def test_bulk_create_transactions_dedups(client):
    client.post("/api/transactions", json=_txn())
    r = client.post("/api/transactions/bulk", json=[_txn(), _txn(code="TSLA")])
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_transactions_validation_aborts(client):
    r = client.post("/api/transactions/bulk", json=[_txn(), {"date": "2026-01-15"}])
    assert r.status_code == 422


def test_bulk_create_transactions_empty(client):
    assert client.post("/api/transactions/bulk", json=[]).json() == {
        "created": 0,
        "skipped": 0,
        "errors": [],
    }
