"""Tests for custom category CRUD API."""

from unittest.mock import patch


def _mock_store(tmp_path):
    """Return a patch context that redirects the categories JSON to tmp_path."""
    import fin.categories_store as store

    return patch.object(store, "LEDGER_CATEGORIES_PATH", tmp_path / "cats.json")


def test_list_categories_includes_builtins(client):
    r = client.get("/api/categories")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert "0001" in ids  # 餐饮 is always present


def test_create_custom_category(client, tmp_path):
    with _mock_store(tmp_path):
        r = client.post(
            "/api/categories",
            json={
                "direction": "expense",
                "name": "健身",
                "bg_color": "#FFFFFF",
                "text_color": "#000000",
            },
        )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "健身"
    assert data["is_builtin"] is False


def test_create_duplicate_category_409(client, tmp_path):
    with _mock_store(tmp_path):
        client.post(
            "/api/categories",
            json={
                "direction": "expense",
                "name": "健身",
                "bg_color": "#FFFFFF",
                "text_color": "#000000",
            },
        )
        r = client.post(
            "/api/categories",
            json={
                "direction": "expense",
                "name": "健身",
                "bg_color": "#FFFFFF",
                "text_color": "#000000",
            },
        )
        assert r.status_code == 409


def test_create_invalid_direction(client):
    r = client.post(
        "/api/categories",
        json={
            "direction": "other",
            "name": "Test",
            "bg_color": "#FFFFFF",
            "text_color": "#000000",
        },
    )
    assert r.status_code == 422


def test_update_custom_category(client, tmp_path):
    with _mock_store(tmp_path):
        cat_id = client.post(
            "/api/categories",
            json={
                "direction": "expense",
                "name": "健身",
                "bg_color": "#FFFFFF",
                "text_color": "#000000",
            },
        ).json()["id"]
        r = client.put(f"/api/categories/{cat_id}", json={"name": "游泳"})
        assert r.status_code == 200
        assert r.json()["name"] == "游泳"


def test_update_builtin_category_403(client):
    r = client.put("/api/categories/0001", json={"name": "新名称"})
    assert r.status_code == 403


def test_update_nonexistent_category_404(client):
    r = client.put("/api/categories/9999", json={"name": "X"})
    assert r.status_code == 404


def test_delete_custom_category(client, tmp_path):
    with _mock_store(tmp_path):
        cat_id = client.post(
            "/api/categories",
            json={
                "direction": "expense",
                "name": "健身",
                "bg_color": "#FFFFFF",
                "text_color": "#000000",
            },
        ).json()["id"]
        r = client.delete(f"/api/categories/{cat_id}")
        assert r.status_code == 204


def test_delete_builtin_category_403(client):
    r = client.delete("/api/categories/0001")
    assert r.status_code == 403


def test_delete_nonexistent_category_404(client):
    r = client.delete("/api/categories/9999")
    assert r.status_code == 404
