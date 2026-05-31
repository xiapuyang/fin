def _income(**kw):
    base = {
        "date": "2026-01-15",
        "source": "Vanguard ETF",
        "category": "dividend",
        "amount": 250.0,
        "currency": "USD",
    }
    base.update(kw)
    return base


def test_bulk_create_income_success(client):
    r = client.post(
        "/api/income/bulk",
        json=[_income(), _income(source="Apple ETF")],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}
    sources = {i["source"] for i in client.get("/api/income").json()}
    assert sources == {"Vanguard ETF", "Apple ETF"}


def test_bulk_create_income_dedups(client):
    client.post("/api/income", json=_income())
    r = client.post(
        "/api/income/bulk",
        json=[_income(), _income(source="Apple ETF")],
    )
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_income_validation_aborts(client):
    r = client.post(
        "/api/income/bulk",
        json=[_income(), {"date": "2026-01-15"}],
    )
    assert r.status_code == 422
    assert client.get("/api/income").json() == []


def test_bulk_create_income_empty(client):
    r = client.post("/api/income/bulk", json=[])
    assert r.json() == {"created": 0, "skipped": 0, "errors": []}
