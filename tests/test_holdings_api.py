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
            "snapshot_name": "2024-01-01",
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
        json={
            "code": "AAPL",
            "market": "US",
            "snapshot_name": "2024-01-01",
            "shares": 10,
            "avg_cost": 200,
        },
    )
    client.post(
        "/api/holdings",
        json={
            "code": "GOOGL",
            "market": "US",
            "snapshot_name": "2024-01-01",
            "shares": 5,
            "avg_cost": 150,
        },
    )
    r = client.get("/api/holdings")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_update_holding(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "TSM",
            "market": "US",
            "snapshot_name": "2024-01-01",
            "shares": 50,
            "avg_cost": 180,
        },
    )
    holding_id = r.json()["id"]
    r = client.put(f"/api/holdings/{holding_id}", json={"shares": 75.0})
    assert r.status_code == 200
    assert r.json()["shares"] == 75.0
    assert r.json()["code"] == "TSM"


def test_delete_holding(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "QQQ",
            "market": "US",
            "snapshot_name": "2024-01-01",
            "shares": 20,
            "avg_cost": 460,
        },
    )
    holding_id = r.json()["id"]
    r = client.delete(f"/api/holdings/{holding_id}")
    assert r.status_code == 204
    r = client.get("/api/holdings")
    assert r.json() == []


def test_create_holding_ca_market(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "RY.TO",
            "name": "Royal Bank",
            "market": "CA",
            "currency": "CAD",
            "snapshot_name": "2024-01-01",
            "shares": 10.0,
            "avg_cost": 130.0,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["market"] == "CA"


def test_create_holding_crypto_market(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "BTC",
            "name": "Bitcoin",
            "market": "CRYPTO",
            "currency": "USD",
            "snapshot_name": "2024-01-01",
            "shares": 0.5,
            "avg_cost": 60000.0,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["market"] == "CRYPTO"


def test_create_holding_invalid_market(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "XYZ",
            "market": "JP",
            "snapshot_name": "2024-01-01",
            "shares": 10,
            "avg_cost": 100,
        },
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
            "realized": 10,
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
        NVDA,$100.00,10,"$1,000.00",买,,"January 1, 2024",
        AAPL,$200.00,20,"$4,000.00",卖,"$300.00","February 1, 2024",
        QQQ,$300.00,30,"$9,000.00",买,,"March 1, 2024",
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
        NVDA,$100.00,10,"$1,000.00",买,,"January 1, 2024",
        BAD,,$50,$0.00,买,,"not a date",
        QQQ,$300.00,30,"$9,000.00",买,,"March 1, 2024",
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


# ── 404 paths ────────────────────────────────────────────────────────────────


def test_update_holding_not_found(client):
    r = client.put("/api/holdings/99999", json={"shares": 10})
    assert r.status_code == 404


def test_update_transaction_not_found(client):
    r = client.put(
        "/api/transactions/99999",
        json={"note": "ghost"},
    )
    assert r.status_code == 404


# ── Account endpoints ─────────────────────────────────────────────────────────


def test_create_and_list_accounts(client):
    r = client.post(
        "/api/accounts",
        json={"name": "IBKR", "currency": "USD"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "IBKR"
    assert data["currency"] == "USD"

    r2 = client.get("/api/accounts")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_delete_account(client):
    r = client.post("/api/accounts", json={"name": "Futu", "currency": "HKD"})
    account_id = r.json()["id"]
    r = client.delete(f"/api/accounts/{account_id}")
    assert r.status_code == 204
    assert client.get("/api/accounts").json() == []


# ── Account cascade rename ────────────────────────────────────────────────────


def _seed_account_with_children(client, name="IBKR"):
    """Create account + one holding + one transaction + one income, all tagged with name."""
    acct_id = client.post(
        "/api/accounts", json={"name": name, "currency": "USD"}
    ).json()["id"]
    code = name[:4].upper()
    client.post(
        "/api/holdings",
        json={
            "code": code,
            "market": "US",
            "snapshot_name": "2024-01-01",
            "shares": 10,
            "avg_cost": 200,
            "account": name,
        },
    )
    client.post(
        "/api/transactions",
        json={
            "date": "2024-01-01",
            "code": code,
            "side": "buy",
            "shares": 10,
            "price": 200,
            "currency": "USD",
            "account": name,
        },
    )
    client.post(
        "/api/income",
        json={
            "date": "2024-01-01",
            "source": f"div-{name}",
            "category": "dividend",
            "amount": 50,
            "currency": "USD",
            "account": name,
        },
    )
    return acct_id


def test_rename_account_cascades_to_holdings_transactions_income(client):
    acct_id = _seed_account_with_children(client, "IBKR")
    r = client.put(f"/api/accounts/{acct_id}", json={"name": "IBKR-2024"})
    assert r.status_code == 200

    holdings = client.get("/api/holdings").json()
    assert all(h["account"] == "IBKR-2024" for h in holdings)

    txns = client.get("/api/transactions").json()
    assert all(t["account"] == "IBKR-2024" for t in txns)

    income = client.get("/api/income").json()
    assert all(i["account"] == "IBKR-2024" for i in income)


def test_rename_account_non_name_field_does_not_cascade(client):
    acct_id = _seed_account_with_children(client, "TD")
    client.put(f"/api/accounts/{acct_id}", json={"note": "updated note"})

    holdings = client.get("/api/holdings").json()
    assert all(h["account"] == "TD" for h in holdings if h["account"])

    txns = client.get("/api/transactions").json()
    assert all(t["account"] == "TD" for t in txns if t["account"])

    income = client.get("/api/income").json()
    assert all(i["account"] == "TD" for i in income if i["account"])


# ── Account cascade delete ────────────────────────────────────────────────────


def test_delete_account_cascades_to_holdings_transactions_income(client):
    acct_id = _seed_account_with_children(client, "Futu")
    r = client.delete(f"/api/accounts/{acct_id}")
    assert r.status_code == 204

    assert client.get("/api/holdings").json() == []
    assert client.get("/api/transactions").json() == []
    assert client.get("/api/income").json() == []


def test_delete_account_only_removes_its_own_children(client):
    acct_a = _seed_account_with_children(client, "Futu")
    _seed_account_with_children(client, "Moomoo")

    client.delete(f"/api/accounts/{acct_a}")

    assert len(client.get("/api/holdings").json()) == 1
    assert len(client.get("/api/transactions").json()) == 1
    assert len(client.get("/api/income").json()) == 1


# ── Validation edge cases ─────────────────────────────────────────────────────


def test_holding_negative_shares_invalid(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "TSLA",
            "market": "US",
            "snapshot_name": "2024-01-01",
            "shares": -1,
            "avg_cost": 100,
        },
    )
    assert r.status_code == 422


def test_holding_zero_shares_invalid(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "TSLA",
            "market": "US",
            "snapshot_name": "2024-01-01",
            "shares": 0,
            "avg_cost": 100,
        },
    )
    assert r.status_code == 422


def test_holding_missing_snapshot_name_invalid(client):
    r = client.post(
        "/api/holdings",
        json={"code": "TSLA", "market": "US", "shares": 10, "avg_cost": 100},
    )
    assert r.status_code == 422


def test_holding_invalid_snapshot_name_format(client):
    r = client.post(
        "/api/holdings",
        json={
            "code": "TSLA",
            "market": "US",
            "snapshot_name": "Jan 2024",
            "shares": 10,
            "avg_cost": 100,
        },
    )
    assert r.status_code == 422


def test_transaction_negative_shares_invalid(client):
    r = client.post(
        "/api/transactions",
        json={
            "date": "2024-01-01",
            "code": "AAPL",
            "side": "buy",
            "shares": -5,
            "price": 100,
        },
    )
    assert r.status_code == 422


# ── CSV import edge cases ─────────────────────────────────────────────────────


def test_import_unknown_side_skipped(client):
    csv_content = (
        "Name,买卖价格,买卖数量,买卖金额,交易,卖出盈利,日期,🔑 关键词\n"
        'NVDA,$100.00,10,"$1,000.00",持有,,"January 1, 2024",\n'
    )
    r = client.post(
        "/api/transactions/import",
        files={"file": ("t.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 0
    assert len(data["skipped"]) == 1
    assert "持有" in data["skipped"][0]["reason"]


def test_import_realized_only_row(client):
    """Rows with shares=0 and price=0 but a realized value must import successfully."""
    csv_content = (
        "Name,买卖价格,买卖数量,买卖金额,交易,卖出盈利,日期,🔑 关键词\n"
        'VTI,,,"$0.00",卖,"$500.00","April 1, 2024",\n'
    )
    r = client.post(
        "/api/transactions/import",
        files={"file": ("t.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 1
    assert data["skipped"] == []
    txns = client.get("/api/transactions").json()
    assert txns[0]["shares"] == 0.0
    assert "500" in (txns[0]["note"] or "")


def test_create_holding_for_code_with_existing_transactions(client):
    # Virtual holdings (transaction-only positions) must be convertible to real holdings via POST.
    # This is the invariant the frontend's virtual-holding edit fix relies on.
    client.post(
        "/api/transactions",
        json={
            "date": "2024-01-01",
            "code": "013308",
            "side": "buy",
            "shares": 100,
            "price": 1.0,
        },
    )
    r = client.post(
        "/api/holdings",
        json={
            "code": "013308",
            "market": "CN",
            "snapshot_name": "2024-01-01",
            "shares": 100.0,
            "avg_cost": 1.0,
        },
    )
    assert r.status_code == 201
    assert r.json()["code"] == "013308"
    assert len(client.get("/api/holdings").json()) == 1
