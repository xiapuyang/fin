"""Tests for ledger CRUD, stats, and recurring endpoints."""

import json


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create(client, **kwargs):
    payload = {
        "direction": "expense",
        "name": "Test",
        "date": "2024-03-15",
        "amount": 100.0,
        "currency": "CNY",
        "category": "0001",
        **kwargs,
    }
    return client.post("/api/ledger", json=payload)


# ── CRUD ──────────────────────────────────────────────────────────────────────


def test_create_and_list(client):
    r = _create(client, name="Lunch")
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Lunch"
    assert data["category"] == "0001"
    assert "category_name" in data

    lst = client.get("/api/ledger").json()
    assert lst["total"] == 1
    assert lst["items"][0]["name"] == "Lunch"


def test_create_income(client):
    r = _create(client, direction="income", name="Salary", category="0020")
    assert r.status_code == 201
    assert r.json()["direction"] == "income"


def test_create_invalid_direction(client):
    r = _create(client, direction="other")
    assert r.status_code == 422


def test_create_zero_amount(client):
    r = _create(client, amount=0)
    assert r.status_code == 422


def test_update(client):
    entry_id = _create(client, name="Old").json()["id"]
    r = client.put(f"/api/ledger/{entry_id}", json={"name": "New", "amount": 200.0})
    assert r.status_code == 200
    assert r.json()["name"] == "New"
    assert r.json()["amount"] == 200.0


def test_update_not_found(client):
    r = client.put("/api/ledger/9999", json={"name": "X"})
    assert r.status_code == 404


def test_delete(client):
    entry_id = _create(client).json()["id"]
    assert client.delete(f"/api/ledger/{entry_id}").status_code == 204
    assert client.get("/api/ledger").json()["total"] == 0


def test_list_filters(client):
    _create(client, direction="expense", date="2024-01-10", category="0001")
    _create(client, direction="income", date="2024-06-01", category="0020")

    r = client.get("/api/ledger?direction=expense").json()
    assert all(i["direction"] == "expense" for i in r["items"])

    r = client.get("/api/ledger?start_date=2024-06-01").json()
    assert r["total"] == 1

    r = client.get("/api/ledger?category=0001").json()
    assert all(i["category"] == "0001" for i in r["items"])


def test_list_search(client):
    _create(client, name="Coffee Shop")
    _create(client, name="Groceries")
    r = client.get("/api/ledger?search=coffee").json()
    assert r["total"] == 1
    assert r["items"][0]["name"] == "Coffee Shop"


def test_list_pagination(client):
    for i in range(5):
        _create(client, name=f"Item {i}")
    r = client.get("/api/ledger?page=1&page_size=3").json()
    assert len(r["items"]) == 3
    assert r["total"] == 5
    assert r["pages"] == 2


# ── Years ─────────────────────────────────────────────────────────────────────


def test_years(client):
    _create(client, date="2023-05-01")
    _create(client, date="2024-11-20")
    years = client.get("/api/ledger/years").json()
    assert 2023 in years
    assert 2024 in years
    assert years == sorted(years, reverse=True)


# ── Recurring ─────────────────────────────────────────────────────────────────


def test_recurring_list(client):
    _create(client, name="Netflix", recurring_type="monthly", subcategory="Netflix")
    _create(
        client,
        name="Netflix",
        recurring_type="monthly",
        subcategory="Netflix",
        date="2024-04-15",
    )
    r = client.get("/api/ledger/recurring").json()
    assert len(r) == 1
    assert r[0]["count"] == 2


def test_recurring_series(client):
    _create(
        client,
        name="Spotify",
        recurring_type="monthly",
        subcategory="Spotify",
        date="2024-03-01",
    )
    _create(
        client,
        name="Spotify",
        recurring_type="monthly",
        subcategory="Spotify",
        date="2024-04-01",
    )
    r = client.get(
        "/api/ledger/recurring/series",
        params={
            "recurring_type": "monthly",
            "category": "0001",
            "subcategory": "Spotify",
        },
    ).json()
    assert len(r) == 2


def test_recurring_series_null_subcategory(client):
    """Series lookup with no subcategory should not 500."""
    r = client.get(
        "/api/ledger/recurring/series",
        params={"recurring_type": "monthly", "category": "0001"},
    )
    assert r.status_code == 200


# ── Stats ─────────────────────────────────────────────────────────────────────


def test_stats_empty(client):
    r = client.get("/api/ledger/stats?time_range=30d").json()
    assert r["summary"]["income"] == 0.0
    assert r["summary"]["expense"] == 0.0
    assert r["bars"] == []


def test_stats_with_data(client):
    _create(client, direction="expense", amount=200.0, date="2024-03-10")
    _create(
        client, direction="income", amount=500.0, date="2024-03-12", category="0020"
    )
    r = client.get(
        "/api/ledger/stats",
        params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
    ).json()
    assert r["summary"]["expense"] == 200.0
    assert r["summary"]["income"] == 500.0
    assert r["summary"]["net"] == 300.0


def test_stats_time_ranges(client):
    for tr in ("7d", "30d", "1y", "all"):
        r = client.get(f"/api/ledger/stats?time_range={tr}")
        assert r.status_code == 200


def test_stats_invalid_time_range(client):
    r = client.get("/api/ledger/stats?time_range=bad")
    assert r.status_code == 422


def test_stats_invalid_currency(client):
    r = client.get("/api/ledger/stats?display_currency=EUR")
    assert r.status_code == 422


def test_stats_with_fx_rates(client):
    _create(client, direction="expense", amount=100.0, currency="CNY")
    fx = json.dumps({"USD": 7.24, "HKD": 0.93, "CAD": 5.3, "CNY": 1.0})
    r = client.get(
        "/api/ledger/stats",
        params={"time_range": "all", "display_currency": "USD", "fx_rates": fx},
    ).json()
    # 100 CNY / 7.24 ≈ 13.81 USD
    assert abs(r["summary"]["expense"] - 100.0 / 7.24) < 0.01


def test_stats_invalid_fx_json(client):
    r = client.get("/api/ledger/stats?fx_rates=not-json")
    assert r.status_code == 400


# ── Backfill ──────────────────────────────────────────────────────────────────


def test_backfill_amounts(client):
    _create(client, amount=100.0, currency="CNY")
    fx = {"USD": 7.24, "HKD": 0.93, "CAD": 5.3, "CNY": 1.0}
    r = client.post("/api/ledger/backfill-amounts", json={"fx_rates": fx})
    assert r.status_code == 200
    assert r.json()["updated"] >= 1
