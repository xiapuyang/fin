"""Tests for paginated transaction endpoint and symbol_markets round-trip."""

TXN_BASE = {
    "date": "2024-01-10",
    "code": "AAPL",
    "side": "buy",
    "shares": 10.0,
    "price": 180.0,
    "currency": "USD",
}


def _post_txn(client, **overrides):
    return client.post("/api/transactions", json={**TXN_BASE, **overrides})


# ── /api/transactions/paged ────────────────────────────────────────────────


def test_paged_empty(client):
    r = client.get("/api/transactions/paged")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_paged_returns_all_on_single_page(client):
    for i in range(3):
        _post_txn(client, date=f"2024-01-{i + 1:02d}", code="NVDA")
    r = client.get("/api/transactions/paged?page=1&page_size=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_paged_respects_page_size(client):
    for i in range(5):
        _post_txn(client, date=f"2024-02-{i + 1:02d}", code="TSLA")
    r = client.get("/api/transactions/paged?page=1&page_size=2")
    data = r.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


def test_paged_second_page(client):
    for i in range(5):
        _post_txn(client, date=f"2024-03-{i + 1:02d}", code="GOOG")
    r = client.get("/api/transactions/paged?page=2&page_size=3")
    data = r.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2  # 5 total, 3 on page 1, 2 on page 2


def test_paged_ordered_most_recent_first(client):
    _post_txn(client, date="2024-01-01", code="META")
    _post_txn(client, date="2024-03-01", code="META")
    _post_txn(client, date="2024-02-01", code="META")
    r = client.get("/api/transactions/paged?page_size=10")
    items = r.json()["items"]
    dates = [it["date"] for it in items]
    assert dates == sorted(dates, reverse=True)


def test_paged_filter_by_symbol(client):
    _post_txn(client, code="AAPL", date="2024-01-01")
    _post_txn(client, code="NVDA", date="2024-01-02")
    _post_txn(client, code="AAPL", date="2024-01-03")
    r = client.get("/api/transactions/paged?symbol=AAPL&page_size=10")
    data = r.json()
    assert data["total"] == 2
    assert all(it["code"] == "AAPL" for it in data["items"])


def test_paged_filter_by_account(client):
    _post_txn(client, account="IBKR", date="2024-01-01")
    _post_txn(client, account="TD", date="2024-01-02")
    _post_txn(client, account="IBKR", date="2024-01-03")
    r = client.get("/api/transactions/paged?account=IBKR&page_size=10")
    data = r.json()
    assert data["total"] == 2
    assert all(it["account"] == "IBKR" for it in data["items"])


def test_paged_filter_by_symbol_and_account(client):
    _post_txn(client, code="AAPL", account="IBKR", date="2024-01-01")
    _post_txn(client, code="AAPL", account="TD", date="2024-01-02")
    _post_txn(client, code="NVDA", account="IBKR", date="2024-01-03")
    r = client.get("/api/transactions/paged?symbol=AAPL&account=IBKR&page_size=10")
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["code"] == "AAPL"
    assert data["items"][0]["account"] == "IBKR"


def test_paged_unknown_symbol_returns_empty(client):
    _post_txn(client, code="AAPL", date="2024-01-01")
    r = client.get("/api/transactions/paged?symbol=ZZZZ&page_size=10")
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_paged_page_size_too_large_rejected(client):
    r = client.get("/api/transactions/paged?page_size=9999")
    assert r.status_code == 422


def test_paged_page_zero_rejected(client):
    r = client.get("/api/transactions/paged?page=0")
    assert r.status_code == 422


# ── symbol_markets round-trip ──────────────────────────────────────────────


def _create_account(client, name="TestAcct"):
    r = client.post("/api/accounts", json={"name": name, "currency": "USD"})
    assert r.status_code == 201
    return r.json()


def test_symbol_markets_store_and_retrieve(client):
    acct = _create_account(client)
    mapping = {"013308": "HK", "600519": "SH"}
    r = client.put(f"/api/accounts/{acct['id']}", json={"symbol_markets": mapping})
    assert r.status_code == 200
    assert r.json()["symbol_markets"] == mapping


def test_symbol_markets_clear_with_null(client):
    acct = _create_account(client)
    client.put(f"/api/accounts/{acct['id']}", json={"symbol_markets": {"X": "US"}})
    r = client.put(f"/api/accounts/{acct['id']}", json={"symbol_markets": None})
    assert r.status_code == 200
    assert r.json()["symbol_markets"] is None


def test_symbol_markets_update_replaces_map(client):
    acct = _create_account(client)
    client.put(f"/api/accounts/{acct['id']}", json={"symbol_markets": {"A": "US"}})
    r = client.put(f"/api/accounts/{acct['id']}", json={"symbol_markets": {"B": "HK"}})
    assert r.status_code == 200
    assert r.json()["symbol_markets"] == {"B": "HK"}


def test_symbol_markets_empty_dict(client):
    acct = _create_account(client)
    r = client.put(f"/api/accounts/{acct['id']}", json={"symbol_markets": {}})
    assert r.status_code == 200


def test_symbol_markets_persists_across_get(client):
    acct = _create_account(client)
    mapping = {"SPY": "US"}
    client.put(f"/api/accounts/{acct['id']}", json={"symbol_markets": mapping})
    r = client.get("/api/accounts")
    accounts = r.json()
    found = next(a for a in accounts if a["id"] == acct["id"])
    assert found["symbol_markets"] == mapping


# ── account IDOR fix ───────────────────────────────────────────────────────


def test_account_update_returns_404_for_nonexistent_id(client):
    r = client.put("/api/accounts/99999", json={"note": "x"})
    assert r.status_code == 404


def test_account_delete_nonexistent_is_noop(client):
    r = client.delete("/api/accounts/99999")
    assert r.status_code == 204
