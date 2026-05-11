"""Tests for balance sheet accounts, snapshots, items, copy, and import endpoints."""

import io


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_snap(client, date="2025-01-01", label="Test Snap", note=None):
    payload = {"snapshot_date": date, "label": label}
    if note:
        payload["note"] = note
    return client.post("/api/balance/snapshots", json=payload)


def _create_item(
    client, snapshot_id, name="Cash", side="asset", amount=1000.0, **kwargs
):
    payload = {
        "snapshot_id": snapshot_id,
        "name": name,
        "category": "现金",
        "side": side,
        "amount": amount,
        "currency": "CNY",
        **kwargs,
    }
    return client.post("/api/balance/items", json=payload)


def _create_account(client, name="招商银行", parent_id=None):
    payload = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    return client.post("/api/balance/accounts", json=payload)


# ── Accounts ──────────────────────────────────────────────────────────────────


def test_account_create_and_list(client):
    r = _create_account(client)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "招商银行"
    assert data["parent_id"] is None

    lst = client.get("/api/balance/accounts").json()
    assert len(lst) == 1
    assert lst[0]["name"] == "招商银行"


def test_account_create_with_parent(client):
    parent_id = _create_account(client, "招商银行").json()["id"]
    r = _create_account(client, "人民币账户", parent_id=parent_id)
    assert r.status_code == 201
    assert r.json()["parent_id"] == parent_id


def test_account_update(client):
    acc_id = _create_account(client).json()["id"]
    r = client.put(f"/api/balance/accounts/{acc_id}", json={"name": "新名称"})
    assert r.status_code == 200
    assert r.json()["name"] == "新名称"


def test_account_update_not_found(client):
    r = client.put("/api/balance/accounts/9999", json={"name": "X"})
    assert r.status_code == 404


def test_account_delete(client):
    acc_id = _create_account(client).json()["id"]
    r = client.delete(f"/api/balance/accounts/{acc_id}")
    assert r.status_code == 204
    assert client.get("/api/balance/accounts").json() == []


def test_account_delete_nullifies_item_refs(client):
    snap_id = _create_snap(client).json()["id"]
    acc_id = _create_account(client).json()["id"]
    item_id = _create_item(client, snap_id, account_id=acc_id).json()["id"]

    client.delete(f"/api/balance/accounts/{acc_id}")

    item = client.get(f"/api/balance/snapshots/{snap_id}/items").json()[0]
    assert item["id"] == item_id
    assert item["account_id"] is None
    assert item["account_name"] is None


def test_account_delete_nullifies_sub_account_id(client):
    parent_id = _create_account(client, name="Parent").json()["id"]
    child_id = _create_account(client, name="Child", parent_id=parent_id).json()["id"]
    snap_id = _create_snap(client).json()["id"]
    payload = {
        "snapshot_id": snap_id,
        "name": "Sub item",
        "category": "现金",
        "side": "asset",
        "amount": 100.0,
        "currency": "CNY",
        "account_id": parent_id,
        "sub_account_id": child_id,
    }
    client.post("/api/balance/items", json=payload).json()["id"]
    client.delete(f"/api/balance/accounts/{child_id}")
    items = client.get(f"/api/balance/snapshots/{snap_id}/items").json()
    assert items[0]["sub_account_id"] is None
    assert items[0]["sub_account_name"] is None


def test_account_delete_not_found(client):
    r = client.delete("/api/balance/accounts/9999")
    assert r.status_code == 404


# ── Snapshots ─────────────────────────────────────────────────────────────────


def test_snapshot_create_and_list(client):
    r = _create_snap(client, date="2025-03-01", label="Q1")
    assert r.status_code == 201
    data = r.json()
    assert data["snapshot_date"] == "2025-03-01"
    assert data["label"] == "Q1"
    assert data["item_count"] == 0

    lst = client.get("/api/balance/snapshots").json()
    assert len(lst) == 1
    assert lst[0]["label"] == "Q1"


def test_snapshot_update(client):
    snap_id = _create_snap(client).json()["id"]
    r = client.put(f"/api/balance/snapshots/{snap_id}", json={"label": "Updated"})
    assert r.status_code == 200
    assert r.json()["label"] == "Updated"


def test_snapshot_update_not_found(client):
    r = client.put("/api/balance/snapshots/9999", json={"label": "X"})
    assert r.status_code == 404


def test_snapshot_delete(client):
    snap_id = _create_snap(client).json()["id"]
    r = client.delete(f"/api/balance/snapshots/{snap_id}")
    assert r.status_code == 204
    assert client.get("/api/balance/snapshots").json() == []


def test_snapshot_delete_cascades_items(client):
    snap_id = _create_snap(client).json()["id"]
    _create_item(client, snap_id)
    client.delete(f"/api/balance/snapshots/{snap_id}")
    assert client.get("/api/balance/snapshots").json() == []
    assert client.get("/api/balance/items").json() == []


def test_snapshot_delete_not_found(client):
    r = client.delete("/api/balance/snapshots/9999")
    assert r.status_code == 404


def test_snapshot_item_count(client):
    snap_id = _create_snap(client).json()["id"]
    _create_item(client, snap_id, name="A")
    _create_item(client, snap_id, name="B")
    snap = client.get("/api/balance/snapshots").json()[0]
    assert snap["item_count"] == 2


# ── Copy snapshot ─────────────────────────────────────────────────────────────


def test_copy_snapshot_basic(client):
    snap_id = _create_snap(client, date="2025-01-01", label="Orig").json()["id"]
    _create_item(client, snap_id, name="Cash", amount=5000.0)
    _create_item(
        client, snap_id, name="Debt", side="liability", amount=2000.0, category="贷款"
    )

    r = client.post(f"/api/balance/snapshots/{snap_id}/copy", json={})
    assert r.status_code == 201
    copy = r.json()
    assert copy["label"] == "Orig (副本)"
    assert copy["item_count"] == 2

    items = client.get(f"/api/balance/snapshots/{copy['id']}/items").json()
    assert len(items) == 2
    names = {i["name"] for i in items}
    assert names == {"Cash", "Debt"}


def test_copy_snapshot_with_new_label_and_date(client):
    snap_id = _create_snap(client).json()["id"]
    r = client.post(
        f"/api/balance/snapshots/{snap_id}/copy",
        json={"new_label": "New Label", "new_date": "2026-01-01"},
    )
    assert r.status_code == 201
    copy = r.json()
    assert copy["label"] == "New Label"
    assert copy["snapshot_date"] == "2026-01-01"


def test_copy_snapshot_not_found(client):
    r = client.post("/api/balance/snapshots/9999/copy", json={})
    assert r.status_code == 404


def test_copy_snapshot_conflict_returns_409(client):
    snap_id = _create_snap(client, date="2025-01-01", label="Orig").json()["id"]
    client.post(f"/api/balance/snapshots/{snap_id}/copy", json={})
    r = client.post(f"/api/balance/snapshots/{snap_id}/copy", json={})
    assert r.status_code == 409


# ── Items ─────────────────────────────────────────────────────────────────────


def test_item_create_and_list(client):
    snap_id = _create_snap(client).json()["id"]
    r = _create_item(client, snap_id, name="招行存款", amount=50000.0)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "招行存款"
    assert data["side"] == "asset"
    assert data["amount"] == 50000.0
    assert data["snapshot_date"] == "2025-01-01"

    lst = client.get(f"/api/balance/snapshots/{snap_id}/items").json()
    assert len(lst) == 1


def test_item_create_with_account(client):
    snap_id = _create_snap(client).json()["id"]
    acc_id = _create_account(client, "招商银行").json()["id"]
    r = _create_item(client, snap_id, account_id=acc_id)
    assert r.status_code == 201
    data = r.json()
    assert data["account_id"] == acc_id
    assert data["account_name"] == "招商银行"


def test_item_create_invalid_category(client):
    snap_id = _create_snap(client).json()["id"]
    r = _create_item(client, snap_id, category="不存在的分类")
    assert r.status_code == 422


def test_item_create_invalid_side(client):
    snap_id = _create_snap(client).json()["id"]
    payload = {
        "snapshot_id": snap_id,
        "name": "X",
        "category": "现金",
        "side": "unknown",
        "amount": 100.0,
    }
    r = client.post("/api/balance/items", json=payload)
    assert r.status_code == 422


def test_item_update(client):
    snap_id = _create_snap(client).json()["id"]
    item_id = _create_item(client, snap_id, amount=100.0).json()["id"]
    r = client.put(f"/api/balance/items/{item_id}", json={"amount": 200.0})
    assert r.status_code == 200
    assert r.json()["amount"] == 200.0


def test_item_update_not_found(client):
    r = client.put("/api/balance/items/9999", json={"amount": 1.0})
    assert r.status_code == 404


def test_item_delete(client):
    snap_id = _create_snap(client).json()["id"]
    item_id = _create_item(client, snap_id).json()["id"]
    r = client.delete(f"/api/balance/items/{item_id}")
    assert r.status_code == 204
    assert client.get(f"/api/balance/snapshots/{snap_id}/items").json() == []


def test_item_delete_not_found(client):
    r = client.delete("/api/balance/items/9999")
    assert r.status_code == 404


def test_list_all_items(client):
    s1 = _create_snap(client, date="2025-01-01", label="S1").json()["id"]
    s2 = _create_snap(client, date="2025-06-01", label="S2").json()["id"]
    _create_item(client, s1, name="A")
    _create_item(client, s2, name="B")

    all_items = client.get("/api/balance/items").json()
    assert len(all_items) == 2
    names = {i["name"] for i in all_items}
    assert names == {"A", "B"}


def test_item_with_extra_fields(client):
    snap_id = _create_snap(client).json()["id"]
    payload = {
        "snapshot_id": snap_id,
        "name": "房贷",
        "category": "贷款",
        "side": "liability",
        "amount": 2000000.0,
        "interest_rate": 0.0365,
        "monthly_payment": 10400.0,
        "start_date": "2022-01-01",
        "end_date": "2052-01-01",
    }
    r = client.post("/api/balance/items", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["interest_rate"] == 0.0365
    assert data["monthly_payment"] == 10400.0
    assert data["start_date"] == "2022-01-01"
    assert data["end_date"] == "2052-01-01"


# ── Import ────────────────────────────────────────────────────────────────────


def test_import_creates_snapshots_and_items(client):
    csv_content = (
        "资产项,金额,资产 OR 负债,分类,关联资产负债表\n"
        "招行存款,CN¥50000,资产,现金,1819d2dbf46d8030acf2eccb7031086c\n"
        "房贷余额,CN¥200000,负债,贷款,1819d2dbf46d8030acf2eccb7031086c\n"
    )
    f = io.BytesIO(csv_content.encode("utf-8"))
    r = client.post("/api/balance/import", files={"file": ("test.csv", f, "text/csv")})
    assert r.status_code == 200
    data = r.json()
    assert data["snapshots_created"] == 1
    assert data["items_imported"] == 2
    assert data["skipped"] == []

    snaps = client.get("/api/balance/snapshots").json()
    assert len(snaps) == 1
    assert snaps[0]["snapshot_date"] == "2025-01-20"


def test_import_dedup_on_reimport(client):
    csv_content = (
        "资产项,金额,资产 OR 负债,分类,关联资产负债表\n"
        "招行存款,CN¥50000,资产,现金,1819d2dbf46d8030acf2eccb7031086c\n"
    )

    def _post():
        f = io.BytesIO(csv_content.encode("utf-8"))
        return client.post(
            "/api/balance/import", files={"file": ("test.csv", f, "text/csv")}
        )

    r1 = _post()
    assert r1.json()["items_imported"] == 1

    r2 = _post()
    assert r2.json()["items_imported"] == 0
    assert r2.json()["snapshots_created"] == 0


def test_import_skips_empty_name(client):
    csv_content = (
        "资产项,金额,资产 OR 负债,分类,关联资产负债表\n"
        ",CN¥100,资产,现金,1819d2dbf46d8030acf2eccb7031086c\n"
    )
    f = io.BytesIO(csv_content.encode("utf-8"))
    r = client.post("/api/balance/import", files={"file": ("test.csv", f, "text/csv")})
    data = r.json()
    assert data["items_imported"] == 0
    assert data["skipped"][0]["reason"] == "empty name"


def test_import_skips_unknown_snapshot_ref(client):
    csv_content = (
        "资产项,金额,资产 OR 负债,分类,关联资产负债表\n"
        "Test,CN¥100,资产,现金,aaaabbbbccccddddeeeeffffaaaabbbb\n"
    )
    f = io.BytesIO(csv_content.encode("utf-8"))
    r = client.post("/api/balance/import", files={"file": ("test.csv", f, "text/csv")})
    data = r.json()
    assert data["items_imported"] == 0
    assert any("no recognized snapshot ref" in s["reason"] for s in data["skipped"])


def test_import_skips_unparseable_amount(client):
    csv_content = (
        "资产项,金额,资产 OR 负债,分类,关联资产负债表\n"
        "测试项,N/A,资产,现金,1819d2dbf46d8030acf2eccb7031086c\n"
    )
    f = io.BytesIO(csv_content.encode("utf-8"))
    r = client.post("/api/balance/import", files={"file": ("test.csv", f, "text/csv")})
    data = r.json()
    assert data["items_imported"] == 0
    assert any("unparseable amount" in s["reason"] for s in data["skipped"])


def test_import_skips_unknown_side(client):
    csv_content = (
        "资产项,金额,资产 OR 负债,分类,关联资产负债表\n"
        "Test,CN¥100,未知,现金,1819d2dbf46d8030acf2eccb7031086c\n"
    )
    f = io.BytesIO(csv_content.encode("utf-8"))
    r = client.post("/api/balance/import", files={"file": ("test.csv", f, "text/csv")})
    data = r.json()
    assert data["items_imported"] == 0
    assert any("unknown side" in s["reason"] for s in data["skipped"])
