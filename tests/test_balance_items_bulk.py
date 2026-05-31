def _snapshot(client):
    r = client.post(
        "/api/balance/snapshots",
        json={"snapshot_date": "2026-05-31", "label": "test"},
    )
    return r.json()["id"]


def _item(snapshot_id, **kw):
    base = {
        "snapshot_id": snapshot_id,
        "name": "Checking",
        "category": "现金",
        "side": "asset",
        "amount": 15000.0,
        "currency": "USD",
    }
    base.update(kw)
    return base


def test_bulk_create_balance_items_success(client):
    sid = _snapshot(client)
    r = client.post(
        "/api/balance/items/bulk",
        json=[_item(sid), _item(sid, name="Savings")],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}


def test_bulk_create_balance_items_dedups_within_snapshot(client):
    sid = _snapshot(client)
    client.post("/api/balance/items", json=_item(sid))
    r = client.post(
        "/api/balance/items/bulk",
        json=[_item(sid), _item(sid, name="Savings")],
    )
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_balance_items_validation_aborts(client):
    sid = _snapshot(client)
    r = client.post("/api/balance/items/bulk", json=[_item(sid), {}])
    assert r.status_code == 422


def test_bulk_create_balance_items_missing_snapshot_id_422(client):
    """Server does NOT look up by date; skill is responsible for stamping snapshot_id."""
    payload = [
        {
            "name": "Checking",
            "category": "现金",
            "side": "asset",
            "amount": 15000.0,
            "currency": "USD",
            # snapshot_id intentionally omitted
        }
    ]
    r = client.post("/api/balance/items/bulk", json=payload)
    assert r.status_code == 422


def test_bulk_create_balance_items_empty(client):
    r = client.post("/api/balance/items/bulk", json=[])
    assert r.json() == {"created": 0, "skipped": 0, "errors": []}
