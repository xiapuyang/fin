"""Tests for POST /api/balance/accounts/bulk."""


def test_bulk_create_balance_accounts_flat(client):
    r = client.post(
        "/api/balance/accounts/bulk",
        json=[{"name": "IB"}, {"name": "WealthSimple"}],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}
    accts = client.get("/api/balance/accounts").json()
    assert {a["name"] for a in accts} == {"IB", "WealthSimple"}


def test_bulk_create_balance_accounts_tree(client):
    r = client.post(
        "/api/balance/accounts/bulk",
        json=[
            {"name": "IB"},
            {"name": "股票账户", "parent_name": "IB"},
            {"name": "现金", "parent_name": "IB"},
        ],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 3, "skipped": 0, "errors": []}
    by_name = {a["name"]: a for a in client.get("/api/balance/accounts").json()}
    assert by_name["股票账户"]["parent_id"] == by_name["IB"]["id"]
    assert by_name["现金"]["parent_id"] == by_name["IB"]["id"]


def test_bulk_create_balance_accounts_resolves_existing_parent(client):
    client.post("/api/balance/accounts", json={"name": "IB"})
    r = client.post(
        "/api/balance/accounts/bulk",
        json=[{"name": "股票账户", "parent_name": "IB"}],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 1, "skipped": 0, "errors": []}
    by_name = {a["name"]: a for a in client.get("/api/balance/accounts").json()}
    assert by_name["股票账户"]["parent_id"] == by_name["IB"]["id"]


def test_bulk_create_balance_accounts_unknown_parent_aborts(client):
    r = client.post(
        "/api/balance/accounts/bulk",
        json=[{"name": "股票账户", "parent_name": "DoesNotExist"}],
    )
    assert r.status_code == 400
    assert "DoesNotExist" in r.text
    assert client.get("/api/balance/accounts").json() == []


def test_bulk_create_balance_accounts_skip_duplicate(client):
    client.post("/api/balance/accounts", json={"name": "IB"})
    r = client.post(
        "/api/balance/accounts/bulk",
        json=[{"name": "IB"}, {"name": "WealthSimple"}],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}
