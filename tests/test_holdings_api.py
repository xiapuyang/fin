import io
import textwrap


def test_create_holding(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "NVDA",
            "name": "Nvidia",
            "market": "US",
            "currency": "USD",
            "shares": 100.0,
            "avg_cost": 120.0,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["id"]
    assert data["code"] == "NVDA"
    assert data["shares"] == 100.0


def test_list_holdings(client):
    client.post(
        "/api/holdings",
        json={"code": "AAPL", "market": "US", "shares": 10, "avg_cost": 200},
    )
    client.post(
        "/api/holdings",
        json={"code": "GOOGL", "market": "US", "shares": 5, "avg_cost": 150},
    )
    r = client.get("/api/holdings")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_update_holding(client):
    r = client.post(
        "/api/holdings",
        json={"code": "TSM", "market": "US", "shares": 50, "avg_cost": 180},
    )
    holding_id = r.json()["id"]
    r = client.put(f"/api/holdings/{holding_id}", json={"shares": 75.0})
    assert r.status_code == 200
    assert r.json()["shares"] == 75.0
    assert r.json()["code"] == "TSM"


def test_delete_holding(client):
    r = client.post(
        "/api/holdings",
        json={"code": "QQQ", "market": "US", "shares": 20, "avg_cost": 460},
    )
    holding_id = r.json()["id"]
    r = client.delete(f"/api/holdings/{holding_id}")
    assert r.status_code == 204
    r = client.get("/api/holdings")
    assert r.json() == []


def test_create_holding_invalid_market(client):
    r = client.post(
        "/api/holdings",
        json={"code": "XYZ", "market": "JP", "shares": 10, "avg_cost": 100},
    )
    assert r.status_code == 422


def test_create_transaction(client):
    r = client.post(
        "/api/transactions",
        json={
            "date": "2024-06-12",
            "code": "NVDA",
            "side": "buy",
            "shares": 100,
            "price": 78.4,
            "currency": "USD",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["id"]
    assert data["side"] == "buy"


def test_create_transaction_invalid_side(client):
    r = client.post(
        "/api/transactions",
        json={
            "date": "2024-01-01",
            "code": "AAPL",
            "side": "hold",
            "shares": 10,
            "price": 150,
        },
    )
    assert r.status_code == 422


def test_list_transactions(client):
    client.post(
        "/api/transactions",
        json={
            "date": "2024-01-01",
            "code": "A",
            "side": "buy",
            "shares": 1,
            "price": 10,
        },
    )
    client.post(
        "/api/transactions",
        json={
            "date": "2024-02-01",
            "code": "B",
            "side": "sell",
            "shares": 1,
            "price": 20,
        },
    )
    r = client.get("/api/transactions")
    assert r.status_code == 200
    assert len(r.json()) == 2
    # ordered by date desc
    assert r.json()[0]["date"] == "2024-02-01"


def test_update_transaction(client):
    r = client.post(
        "/api/transactions",
        json={
            "date": "2024-01-01",
            "code": "AAPL",
            "side": "buy",
            "shares": 10,
            "price": 150,
        },
    )
    txn_id = r.json()["id"]
    r = client.put(f"/api/transactions/{txn_id}", json={"note": "updated note"})
    assert r.status_code == 200
    assert r.json()["note"] == "updated note"
    assert r.json()["price"] == 150.0


def test_delete_transaction(client):
    r = client.post(
        "/api/transactions",
        json={
            "date": "2024-01-01",
            "code": "AAPL",
            "side": "buy",
            "shares": 10,
            "price": 150,
        },
    )
    txn_id = r.json()["id"]
    r = client.delete(f"/api/transactions/{txn_id}")
    assert r.status_code == 204
    assert client.get("/api/transactions").json() == []


def test_import_transactions_notion_csv(client):
    csv_content = textwrap.dedent("""\
        Name,买卖价格,买卖数量,买卖金额,交易,卖出盈利,日期,🔑 关键词
        NVDA,$78.40,100,"$7,840.00",买,,"June 12, 2024",
        AAPL,$235.40,30,"$7,062.00",卖,"$1,803.00","January 9, 2025",
        QQQ,$462.10,60,"$27,726.00",买,,"March 21, 2025",
    """)
    r = client.post(
        "/api/transactions/import",
        files={"file": ("trades.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 3
    assert data["skipped"] == []
    assert len(client.get("/api/transactions").json()) == 3


def test_import_transactions_skips_bad_rows(client):
    csv_content = textwrap.dedent("""\
        Name,买卖价格,买卖数量,买卖金额,交易,卖出盈利,日期,🔑 关键词
        NVDA,$78.40,100,"$7,840.00",买,,"June 12, 2024",
        BAD,,$50,$0.00,买,,"not a date",
        QQQ,$462.10,60,"$27,726.00",买,,"March 21, 2025",
    """)
    r = client.post(
        "/api/transactions/import",
        files={"file": ("trades.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 2
    assert len(data["skipped"]) == 1


def test_create_income(client):
    r = client.post(
        "/api/income",
        json={
            "date": "2024-12-15",
            "source": "NVDA 分红",
            "category": "dividend",
            "amount": 320.0,
            "currency": "USD",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["id"]
    assert data["category"] == "dividend"


def test_create_income_invalid_amount(client):
    r = client.post(
        "/api/income",
        json={
            "date": "2024-01-01",
            "source": "test",
            "category": "dividend",
            "amount": -10,
            "currency": "USD",
        },
    )
    assert r.status_code == 422


def test_update_income_not_found(client):
    r = client.put("/api/income/99999", json={"note": "x"})
    assert r.status_code == 404


def test_delete_income(client):
    r = client.post(
        "/api/income",
        json={
            "date": "2024-01-01",
            "source": "div",
            "category": "dividend",
            "amount": 100,
        },
    )
    income_id = r.json()["id"]
    r = client.delete(f"/api/income/{income_id}")
    assert r.status_code == 204
    assert client.get("/api/income").json() == []
