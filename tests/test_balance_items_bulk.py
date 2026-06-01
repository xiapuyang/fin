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
    # Use different categories so the two items have distinct natural keys.
    r = client.post(
        "/api/balance/items/bulk",
        json=[_item(sid, category="现金"), _item(sid, category="投资")],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}


def test_bulk_create_balance_items_dedups_within_snapshot(client):
    sid = _snapshot(client)
    # Pre-insert one item with category="现金".
    client.post("/api/balance/items", json=_item(sid, category="现金"))
    # Bulk: first item matches the pre-inserted row; second has a different category.
    r = client.post(
        "/api/balance/items/bulk",
        json=[_item(sid, category="现金"), _item(sid, category="投资")],
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


def test_bulk_create_skips_duplicates_within_input(client):
    sid = _snapshot(client)
    payload = [_item(sid), _item(sid)]
    r = client.post("/api/balance/items/bulk", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 1
    assert body["skipped"] == 1


def test_bulk_create_dedups_same_natural_key_different_name(client):
    """Two rows with identical (snapshot_id, side, account_id=null, sub_account_id=null,
    category) but different name/value must not cause IntegrityError.
    The second row should be counted as skipped, not crash with 500.
    """
    sid = _snapshot(client)
    row_a = _item(
        sid,
        account_id=None,
        sub_account_id=None,
        category="现金",
        name="Wallet A",
        amount=100.0,
    )
    row_b = _item(
        sid,
        account_id=None,
        sub_account_id=None,
        category="现金",
        name="Wallet B",
        amount=200.0,
    )
    r = client.post("/api/balance/items/bulk", json=[row_a, row_b])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 1
    assert body["skipped"] == 1
    assert body["errors"] == []
