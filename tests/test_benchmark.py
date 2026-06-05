"""Tests for the benchmark feature: xirr(), nearest_price(), simulate_scheme(), and API endpoints."""

from unittest.mock import patch

import pytest

from fin.services.benchmark_service import (
    nearest_price,
    xirr,
    _serialize_income,
    simulate_scheme,
)
from fin.services.benchmark_scheduler import (
    _seconds_until_next_6am_utc,
    _seconds_until_next_hour,
)


# ── xirr() ───────────────────────────────────────────────────────────────────


def test_xirr_simple_doubling():
    """Deposit $100 on Jan 1, receive $200 one year later → ~100% XIRR."""
    flows = [("2023-01-01", -100.0), ("2024-01-01", 200.0)]
    result = xirr(flows)
    assert result is not None
    assert 98.0 < result < 102.0


def test_xirr_single_flow_returns_none():
    result = xirr([("2023-01-01", -100.0)])
    assert result is None


def test_xirr_all_outflows_returns_none():
    result = xirr([("2023-01-01", -100.0), ("2024-01-01", -200.0)])
    assert result is None


def test_xirr_all_inflows_returns_none():
    result = xirr([("2023-01-01", 100.0), ("2024-01-01", 200.0)])
    assert result is None


def test_xirr_same_date_returns_none():
    """All flows on the same date: Newton step is zero, should return None not 10.0."""
    flows = [("2024-01-01", -100.0), ("2024-01-01", 110.0)]
    result = xirr(flows)
    assert result is None


def test_xirr_divergent_returns_none():
    """Extremely bad trade: $100 in, get back $0.01 — Newton diverges."""
    flows = [("2020-01-01", -10000.0), ("2024-01-01", 0.01)]
    result = xirr(flows)
    # Either converges to a very negative number or returns None
    assert result is None or result < -90.0


def test_xirr_breakeven():
    """Deposit and withdraw same amount after 1 year → ~0% return."""
    flows = [("2023-01-01", -100.0), ("2024-01-01", 100.0)]
    result = xirr(flows)
    assert result is not None
    assert -2.0 < result < 2.0


# ── nearest_price() ───────────────────────────────────────────────────────────


def test_nearest_price_exact_match():
    series = [{"date": "2024-01-15", "close": 150.0}]
    assert nearest_price(series, "2024-01-15") == 150.0


def test_nearest_price_within_window():
    series = [{"date": "2024-01-17", "close": 155.0}]
    assert nearest_price(series, "2024-01-15") == 155.0


def test_nearest_price_beyond_window():
    series = [{"date": "2024-02-01", "close": 160.0}]
    assert nearest_price(series, "2024-01-15") is None


def test_nearest_price_empty_series():
    assert nearest_price([], "2024-01-15") is None


def test_nearest_price_picks_first_on_or_after():
    series = [
        {"date": "2024-01-14", "close": 140.0},
        {"date": "2024-01-16", "close": 145.0},
        {"date": "2024-01-17", "close": 150.0},
    ]
    assert nearest_price(series, "2024-01-15") == 145.0


# ── _serialize_income() ───────────────────────────────────────────────────────


def test_serialize_income():
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(
            date="2024-01-01", currency="USD", amount=1000.0, category="deposit"
        ),
        SimpleNamespace(
            date="2024-06-01", currency="HKD", amount=500.0, category="withdrawal"
        ),
    ]
    result = _serialize_income(rows)
    assert len(result) == 2
    assert result[0] == {
        "date": "2024-01-01",
        "currency": "USD",
        "amount": 1000.0,
        "category": "deposit",
    }
    assert result[1]["category"] == "withdrawal"


# ── Scheduler timing ──────────────────────────────────────────────────────────


def test_seconds_until_next_hour_positive():
    s = _seconds_until_next_hour()
    assert 1 <= s <= 3600


def test_seconds_until_next_6am_utc_month_boundary():
    """Must not raise ValueError on the last day of any month (regression for ADV-006)."""
    from datetime import datetime, timezone

    end_of_month_dates = [
        datetime(2024, 1, 31, 10, 0, tzinfo=timezone.utc),
        datetime(2024, 3, 31, 7, 0, tzinfo=timezone.utc),
        datetime(2024, 4, 30, 23, 59, tzinfo=timezone.utc),
        datetime(2024, 12, 31, 8, 0, tzinfo=timezone.utc),
    ]
    for dt in end_of_month_dates:
        with patch("fin.services.benchmark_scheduler.datetime") as m:
            m.now.return_value = dt
            result = _seconds_until_next_6am_utc()
            assert result >= 60, f"Expected >= 60 for {dt}"


# ── Benchmark API endpoints ───────────────────────────────────────────────────


@pytest.fixture()
def benchmark_client():
    """Client fixture that also patches benchmark lifecycle to avoid background threads."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from fin.api import app
    from fin.database import Base, get_db, import_all_models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import_all_models()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with (
        patch("fin.api.init_db"),
        patch("fin.api.warn_orphaned_bench_ids"),
        patch("fin.api.start_price_updater"),
        patch("fin.api.start_benchmark_backfill", return_value=lambda: None),
        patch("fin.api.start_benchmark_scheduler", return_value=lambda: None),
        patch("fin.api.stop_benchmark_backfill"),
        patch("fin.api.stop_benchmark_scheduler"),
    ):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _make_benchmark_account(client):
    """Create a benchmark-enabled account and return its ID."""
    r = client.post("/api/accounts", json={"name": "TestBroker", "currency": "USD"})
    assert r.status_code == 201
    acct_id = r.json()["id"]
    r2 = client.put(f"/api/accounts/{acct_id}", json={"benchmark_enabled": True})
    assert r2.status_code == 200
    return acct_id


def test_get_defaults(benchmark_client):
    r = benchmark_client.get("/api/benchmark/defaults")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_get_results_missing_account(benchmark_client):
    r = benchmark_client.get("/api/benchmark/results/9999")
    assert r.status_code == 404


def test_get_results_benchmark_disabled(benchmark_client):
    r = benchmark_client.post(
        "/api/accounts", json={"name": "Disabled", "currency": "USD"}
    )
    acct_id = r.json()["id"]
    r2 = benchmark_client.get(f"/api/benchmark/results/{acct_id}")
    assert r2.status_code == 404


def test_get_results_enabled_no_data(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    r = benchmark_client.get(f"/api/benchmark/results/{acct_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["schemes"] == []


def test_compute_benchmark_disabled_account(benchmark_client):
    r = benchmark_client.post(
        "/api/accounts", json={"name": "NoBenchmark", "currency": "USD"}
    )
    acct_id = r.json()["id"]
    r2 = benchmark_client.post(f"/api/benchmark/compute/{acct_id}")
    assert r2.status_code == 404


def test_put_schemes_unknown_id(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    r = benchmark_client.put(
        f"/api/benchmark/schemes/{acct_id}",
        json={"enabled_defaults": ["nonexistent_scheme_id"]},
    )
    assert r.status_code == 422


def test_put_schemes_valid(benchmark_client):
    """PUT /schemes with empty list should succeed (disable all defaults)."""
    acct_id = _make_benchmark_account(benchmark_client)
    r = benchmark_client.put(
        f"/api/benchmark/schemes/{acct_id}",
        json={"enabled_defaults": []},
    )
    assert r.status_code == 200


def test_list_custom_schemes_empty(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    r = benchmark_client.get(f"/api/benchmark/custom-schemes/{acct_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_delete_custom_scheme(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    payload = {
        "name": "My 60/40",
        "allocations": [
            {"symbol": "SPY", "pct": 60.0},
            {"symbol": "TLT", "pct": 40.0},
        ],
        "cash_pct": 0.0,
    }
    r = benchmark_client.post(f"/api/benchmark/custom-schemes/{acct_id}", json=payload)
    assert r.status_code == 201
    scheme_id = r.json()["id"]

    r2 = benchmark_client.get(f"/api/benchmark/custom-schemes/{acct_id}")
    assert len(r2.json()) == 1

    r3 = benchmark_client.delete(f"/api/benchmark/custom-schemes/{acct_id}/{scheme_id}")
    assert r3.status_code == 200

    r4 = benchmark_client.get(f"/api/benchmark/custom-schemes/{acct_id}")
    assert r4.json() == []


def test_create_custom_scheme_invalid_allocation(benchmark_client):
    """Allocations not summing to ~100 should be rejected."""
    acct_id = _make_benchmark_account(benchmark_client)
    payload = {
        "name": "Bad scheme",
        "allocations": [{"symbol": "SPY", "pct": 50.0}],
        "cash_pct": 0.0,
    }
    r = benchmark_client.post(f"/api/benchmark/custom-schemes/{acct_id}", json=payload)
    assert r.status_code == 422


def test_toggle_custom_scheme_enabled(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    payload = {
        "name": "Toggle test",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    r = benchmark_client.post(f"/api/benchmark/custom-schemes/{acct_id}", json=payload)
    scheme_id = r.json()["id"]

    r2 = benchmark_client.patch(
        f"/api/benchmark/custom-schemes/{acct_id}/{scheme_id}/enabled",
        json={"enabled": False},
    )
    assert r2.status_code == 200

    r3 = benchmark_client.get(f"/api/benchmark/custom-schemes/{acct_id}")
    assert r3.json()[0]["enabled"] == 0


def test_list_portfolio_snapshots_empty(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    r = benchmark_client.get(f"/api/benchmark/portfolio-snapshots/{acct_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_get_history_empty(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    r = benchmark_client.get(f"/api/benchmark/history/{acct_id}")
    assert r.status_code == 200
    data = r.json()
    assert "series" in data


def test_get_prices_known_symbol(benchmark_client):
    """GET /prices returns empty list for a symbol with no cached data (no yfinance call in tests)."""
    _make_benchmark_account(benchmark_client)
    with patch("fin.routers.benchmark.fetch_symbol", return_value=[]):
        r = benchmark_client.get("/api/benchmark/prices?symbol=SPY")
    assert r.status_code == 200


def test_trigger_backfill(benchmark_client):
    acct_id = _make_benchmark_account(benchmark_client)
    with patch(
        "fin.services.benchmark_history_service.backfill_account", return_value=0
    ):
        r = benchmark_client.post(f"/api/benchmark/backfill/{acct_id}")
    assert r.status_code == 202


def test_delete_custom_scheme_wrong_account(benchmark_client):
    """DELETE on a scheme belonging to a different account should 404."""
    acct1 = _make_benchmark_account(benchmark_client)
    r = benchmark_client.post(
        "/api/accounts", json={"name": "TestBroker2", "currency": "USD"}
    )
    acct2 = r.json()["id"]
    benchmark_client.put(f"/api/accounts/{acct2}", json={"benchmark_enabled": True})
    payload = {
        "name": "Scheme A",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    r = benchmark_client.post(f"/api/benchmark/custom-schemes/{acct1}", json=payload)
    scheme_id = r.json()["id"]

    r2 = benchmark_client.delete(f"/api/benchmark/custom-schemes/{acct2}/{scheme_id}")
    assert r2.status_code == 404


def test_account_response_includes_benchmark_fields(benchmark_client):
    """GET /api/accounts should include benchmark_enabled and benchmark_schemes."""
    r = benchmark_client.post(
        "/api/accounts", json={"name": "FieldCheck", "currency": "USD"}
    )
    acct_id = r.json()["id"]
    r2 = benchmark_client.get("/api/accounts")
    accts = {a["id"]: a for a in r2.json()}
    assert "benchmark_enabled" in accts[acct_id]
    assert accts[acct_id]["benchmark_enabled"] is False
    assert accts[acct_id]["benchmark_schemes"] is None


# ── simulate_scheme() ─────────────────────────────────────────────────────────


def _simple_scheme(symbols=("SPY",), pcts=(100.0,), cash_pct=0.0):
    return {
        "id": "test",
        "name": "Test",
        "allocations": [{"symbol": s, "pct": p} for s, p in zip(symbols, pcts)],
        "cash_pct": cash_pct,
    }


def _price_cache(symbol: str, dates_prices: list[tuple[str, float]]) -> dict:
    return {symbol: [{"date": d, "close": p} for d, p in dates_prices]}


def test_simulate_scheme_simple_deposit():
    """Single deposit, known price, terminal above deposit → positive XIRR."""
    scheme = _simple_scheme()
    deposits = [
        {
            "date": "2023-01-01",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        }
    ]
    price_cache = _price_cache("SPY", [("2023-01-01", 100.0), ("2024-01-01", 200.0)])
    current_prices = {"SPY": 200.0}
    fx = {"USD": 1.0, "CNY": 1.0}

    xirr_pct, excluded, terminal = simulate_scheme(
        scheme, deposits, price_cache, current_prices, fx, terminal_date="2024-01-01"
    )
    assert xirr_pct is not None
    assert xirr_pct > 50.0
    assert excluded == 0
    assert terminal > 0


def test_simulate_scheme_missing_price_excludes_deposit():
    """When price is missing for all allocations, deposit is excluded."""
    scheme = _simple_scheme()
    deposits = [
        {
            "date": "2023-01-01",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        }
    ]
    price_cache = {"SPY": []}  # no prices
    current_prices = {}
    fx = {"USD": 1.0}

    xirr_pct, excluded, terminal = simulate_scheme(
        scheme, deposits, price_cache, current_prices, fx, terminal_date="2024-01-01"
    )
    assert excluded == 1
    # Cash accumulated but no shares — terminal is just cash balance
    assert terminal >= 0


def test_simulate_scheme_deposit_predates_launch():
    """Deposit before first price entry → use first available price."""
    scheme = _simple_scheme()
    deposits = [
        {
            "date": "2020-01-01",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        }
    ]
    # Price only available from 2021 onward
    price_cache = _price_cache("SPY", [("2021-01-01", 100.0), ("2024-01-01", 150.0)])
    current_prices = {"SPY": 150.0}
    fx = {"USD": 1.0}

    xirr_pct, excluded, terminal = simulate_scheme(
        scheme, deposits, price_cache, current_prices, fx, terminal_date="2024-01-01"
    )
    assert excluded == 0
    assert terminal > 0


def test_simulate_scheme_withdrawal_reduces_shares():
    """Withdrawal reduces share count proportionally."""
    scheme = _simple_scheme()
    deposits = [
        {
            "date": "2023-01-01",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        },
        {
            "date": "2023-06-01",
            "currency": "USD",
            "amount": 200.0,
            "category": "withdrawal",
        },
    ]
    price_cache = _price_cache(
        "SPY",
        [("2023-01-01", 100.0), ("2023-06-01", 110.0), ("2024-01-01", 120.0)],
    )
    current_prices = {"SPY": 120.0}
    fx = {"USD": 1.0}

    xirr_pct, excluded, terminal = simulate_scheme(
        scheme, deposits, price_cache, current_prices, fx, terminal_date="2024-01-01"
    )
    assert excluded == 0
    # After partial withdrawal the terminal should be less than 10 shares * 120 = 1200
    assert terminal < 1200.0
    assert terminal > 0


def test_simulate_scheme_cash_pct():
    """cash_pct keeps a portion in cash, reducing equity shares (sum(pct)+cash_pct==100)."""
    scheme = {
        "id": "test",
        "name": "Test",
        "allocations": [{"symbol": "SPY", "pct": 50.0}],  # 50% equity
        "cash_pct": 50.0,  # 50% cash → total 100%
    }
    deposits = [
        {
            "date": "2023-01-01",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        }
    ]
    price_cache = _price_cache("SPY", [("2023-01-01", 100.0), ("2024-01-01", 200.0)])
    current_prices = {"SPY": 200.0}
    fx = {"USD": 1.0}

    xirr_pct, excluded, terminal = simulate_scheme(
        scheme, deposits, price_cache, current_prices, fx, terminal_date="2024-01-01"
    )
    # SPY: pct=50 → 0.5 * 1000 / 100 = 5 shares at $100; cash = 0.5 * 1000 = $500
    # Terminal: 5 * 200 + 500 = 1500
    assert terminal == pytest.approx(1500.0, rel=0.01)


def test_simulate_scheme_no_relevant_deposits():
    """Deposits after terminal_date are ignored → empty flows → None XIRR."""
    scheme = _simple_scheme()
    deposits = [
        {
            "date": "2025-01-01",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        }
    ]
    price_cache = _price_cache("SPY", [("2023-01-01", 100.0)])
    current_prices = {"SPY": 100.0}
    fx = {"USD": 1.0}

    xirr_pct, excluded, terminal = simulate_scheme(
        scheme, deposits, price_cache, current_prices, fx, terminal_date="2024-01-01"
    )
    assert xirr_pct is None


# ── compute() early-exit paths ────────────────────────────────────────────────


def test_compute_no_schemes_returns_empty(benchmark_client):
    """Account with benchmark enabled but all defaults disabled → empty schemes list."""
    acct_id = _make_benchmark_account(benchmark_client)
    benchmark_client.put(
        f"/api/benchmark/schemes/{acct_id}", json={"enabled_defaults": []}
    )

    with patch("fin.services.benchmark_service._fetch_fx", return_value={"USD": 1.0}):
        r = benchmark_client.post(f"/api/benchmark/compute/{acct_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["schemes"] == []
    assert data["portfolio_xirr"] is None


def test_compute_no_income_returns_null_xirr(benchmark_client):
    """Account with schemes enabled but no income rows → xirr=None per scheme."""
    acct_id = _make_benchmark_account(benchmark_client)
    # Keep defaults enabled but have no income for this account
    with (
        patch("fin.services.benchmark_service._fetch_fx", return_value={"USD": 1.0}),
        patch("fin.services.price_history_service._fetch_from_provider"),
    ):
        r = benchmark_client.post(f"/api/benchmark/compute/{acct_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["portfolio_xirr"] is None
    assert all(s["xirr"] is None for s in data["schemes"])


# ── warn_orphaned_bench_ids ───────────────────────────────────────────────────


def test_warn_orphaned_bench_ids_no_crash():
    """warn_orphaned_bench_ids() should not raise even with orphaned rows."""
    from unittest.mock import patch
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from fin.database import Base, import_all_models
    from fin.models.benchmark_result import BenchmarkResultModel
    from fin.services.benchmark_service import warn_orphaned_bench_ids

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import_all_models()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        BenchmarkResultModel(
            account_id=1, bench_id="old_scheme_id", computed_date="2024-01-01"
        )
    )
    db.commit()
    with patch("fin.database.SessionLocal", Session):
        warn_orphaned_bench_ids()
    db.close()
    engine.dispose()


# ── _simulate_schemes ─────────────────────────────────────────────────────────


def test_simulate_schemes_empty_list():
    from fin.services.benchmark_service import _simulate_schemes

    results, excluded = _simulate_schemes([], [], {}, {}, {"USD": 7.2, "CNY": 1.0})
    assert results == []
    assert excluded == 0


def test_simulate_schemes_single_scheme():
    from fin.services.benchmark_service import _simulate_schemes

    scheme = {
        "id": "s1",
        "name": "Test",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    income = [
        {
            "date": "2022-01-03",
            "amount": 1000.0,
            "currency": "USD",
            "category": "deposit",
        }
    ]
    series = [
        {"date": "2022-01-03", "close": 400.0},
        {"date": "2024-01-02", "close": 500.0},
    ]
    price_cache = {"SPY": series}
    current_prices = {"SPY": 500.0}
    fx = {"USD": 7.2, "CNY": 1.0}

    results, excluded = _simulate_schemes(
        [scheme], income, price_cache, current_prices, fx
    )
    assert len(results) == 1
    assert results[0]["id"] == "s1"
    assert results[0]["xirr"] is not None
    assert excluded == 0


# ── _price_on_date (binary search) ────────────────────────────────────────────


def test_price_on_date_found():
    from fin.services.benchmark_history_service import _price_on_date

    series = [
        {"date": "2024-01-01", "close": 100.0},
        {"date": "2024-01-02", "close": 101.0},
        {"date": "2024-01-04", "close": 103.0},
    ]
    assert _price_on_date(series, "2024-01-01") == 100.0
    assert _price_on_date(series, "2024-01-02") == 101.0
    assert _price_on_date(series, "2024-01-04") == 103.0


def test_price_on_date_not_found():
    from fin.services.benchmark_history_service import _price_on_date

    series = [
        {"date": "2024-01-01", "close": 100.0},
        {"date": "2024-01-03", "close": 102.0},
    ]
    assert _price_on_date(series, "2024-01-02") is None
    assert _price_on_date(series, "2023-12-31") is None
    assert _price_on_date([], "2024-01-01") is None


# ── _build_holdings_positions ─────────────────────────────────────────────────


def _make_isolated_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from fin.database import Base, import_all_models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import_all_models()
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def test_build_holdings_positions_no_holdings():
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import _build_holdings_positions

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(user_id=MOCK_USER_ID, name="HoldAcct", currency="USD")
    db.add(account)
    db.commit()

    positions = _build_holdings_positions(db, account, {"USD": 7.2, "CNY": 1.0})
    assert positions == {}
    db.close()
    engine.dispose()


# ── _fetch_price_data ─────────────────────────────────────────────────────────


def test_fetch_price_data_no_symbols():
    from fin.services.benchmark_service import _fetch_price_data

    cache, prices = _fetch_price_data([], "2022-01-01")
    assert cache == {}
    assert prices == {}


def test_fetch_price_data_mocked():
    from fin.services.benchmark_service import _fetch_price_data

    fake_series = [{"date": "2022-01-03", "close": 100.0}]
    with (
        patch("fin.services.benchmark_service.fetch_symbol", return_value=fake_series),
        patch(
            "fin.services.benchmark_service._fetch_current_price", return_value=105.0
        ),
    ):
        cache, prices = _fetch_price_data(["SPY"], "2022-01-01")

    assert "SPY" in cache
    assert cache["SPY"] == fake_series
    assert prices.get("SPY") == 105.0


# ── _compute_portfolio_snap_result ────────────────────────────────────────────


def test_compute_portfolio_snap_result_no_snap():
    from fin.services.benchmark_service import _compute_portfolio_snap_result

    engine, Session = _make_isolated_db()
    db = Session()
    result = _compute_portfolio_snap_result(
        db, 999, [], {}, {}, {"USD": 7.2, "CNY": 1.0}
    )
    assert result is None
    db.close()
    engine.dispose()


# ── _write_bench_results ──────────────────────────────────────────────────────


def test_write_bench_results_creates_rows():
    from fin.models.benchmark_result import BenchmarkResultModel
    from fin.services.benchmark_service import _write_bench_results

    engine, Session = _make_isolated_db()
    db = Session()
    _write_bench_results(
        db,
        account_id=1,
        today="2024-01-01",
        portfolio_xirr=5.0,
        portfolio_value_usd=1000.0,
        scheme_results=[],
    )
    rows = db.query(BenchmarkResultModel).all()
    assert len(rows) == 1
    assert rows[0].bench_id == "__portfolio__"
    assert rows[0].xirr == 5.0
    db.close()
    engine.dispose()


# ── backfill_account (direct) ─────────────────────────────────────────────────


def test_backfill_account_disabled_returns_zero():
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import backfill_account

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="BFDisabled", currency="USD", benchmark_enabled="0"
    )
    db.add(account)
    db.commit()
    assert backfill_account(db, account.id) == 0
    db.close()
    engine.dispose()


def test_backfill_account_no_income_returns_zero():
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import backfill_account

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="BFNoIncome", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.commit()
    assert backfill_account(db, account.id) == 0
    db.close()
    engine.dispose()


def test_backfill_account_with_income_runs():
    """backfill_account with income + mocked prices should write result rows."""
    from fin.models.account import AccountModel
    from fin.models.benchmark_result import BenchmarkResultModel
    from fin.models.income import IncomeModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import backfill_account

    engine, Session = _make_isolated_db()
    db = Session()

    account = AccountModel(
        user_id=MOCK_USER_ID, name="BFAcct", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    # Deposit 2 years ago so annual XIRR stays within the -1..100 guard
    db.add(
        IncomeModel(
            user_id=MOCK_USER_ID,
            date="2022-01-03",
            source="dep1",
            category="deposit",
            amount=1000.0,
            currency="USD",
            account="BFAcct",
        )
    )
    db.commit()

    fake_series = [
        {"date": "2022-01-03", "close": 100.0},
        {"date": "2022-07-01", "close": 108.0},
        {"date": "2023-01-03", "close": 115.0},
        {"date": "2023-07-01", "close": 120.0},
        {"date": "2024-01-02", "close": 126.0},
    ]
    fake_scheme = {
        "id": "sp500",
        "name": "S&P 500",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }

    with (
        patch(
            "fin.services.benchmark_service._load_benchmark_defaults",
            return_value=[fake_scheme],
        ),
        patch(
            "fin.services.benchmark_history_service._build_backfill_price_cache",
            return_value={"SPY": fake_series},
        ),
        patch(
            "fin.services.benchmark_service._fetch_fx",
            return_value={"USD": 7.2, "CNY": 1.0},
        ),
        patch(
            "fin.services.benchmark_history_service._build_portfolio_scheme",
            return_value=None,
        ),
    ):
        n = backfill_account(db, account.id)

    assert n > 0
    rows = (
        db.query(BenchmarkResultModel)
        .filter(BenchmarkResultModel.account_id == account.id)
        .all()
    )
    assert len(rows) > 0
    db.close()
    engine.dispose()


# ── compute full path ─────────────────────────────────────────────────────────


def test_compute_with_income_and_prices(benchmark_client):
    """Full compute path: income + mocked prices → results written to DB."""
    acct_id = _make_benchmark_account(benchmark_client)
    account_name = benchmark_client.get("/api/accounts").json()[-1]["name"]

    benchmark_client.post(
        "/api/income",
        json={
            "date": "2022-01-03",
            "source": "test_dep",
            "category": "deposit",
            "amount": 1000.0,
            "currency": "USD",
            "account": account_name,
        },
    )

    fake_series = [
        {"date": "2022-01-03", "close": 400.0},
        {"date": "2024-01-02", "close": 500.0},
    ]
    fake_scheme = {
        "id": "sp500",
        "name": "S&P 500",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }

    with (
        patch(
            "fin.services.benchmark_service._load_benchmark_defaults",
            return_value=[fake_scheme],
        ),
        patch(
            "fin.services.benchmark_service._fetch_fx",
            return_value={"USD": 7.2, "CNY": 1.0},
        ),
        patch("fin.services.benchmark_service.fetch_symbol", return_value=fake_series),
        patch(
            "fin.services.benchmark_service._fetch_current_price", return_value=500.0
        ),
        patch(
            "fin.services.benchmark_service._build_holdings_positions", return_value={}
        ),
    ):
        r = benchmark_client.post(f"/api/benchmark/compute/{acct_id}")

    assert r.status_code == 200
    data = r.json()
    assert data["portfolio_xirr"] is None  # no holdings → portfolio XIRR is None
    assert len(data["schemes"]) >= 1
    scheme_result = next((s for s in data["schemes"] if s["id"] == "sp500"), None)
    assert scheme_result is not None
    assert scheme_result["xirr"] is not None


# ── price_history_service ─────────────────────────────────────────────────────


def test_fetch_symbol_stale_triggers_provider():
    """fetch_symbol should call _fetch_from_provider when no cached rows exist."""
    from fin.services.price_history_service import fetch_symbol

    engine, Session = _make_isolated_db()
    db = Session()
    with patch("fin.services.price_history_service._fetch_from_provider") as mock_fp:
        fetch_symbol(db, "SPY", "2022-01-01")
    mock_fp.assert_called_once()
    db.close()
    engine.dispose()


def test_fetch_from_provider_inserts_rows():
    """_fetch_from_provider should upsert rows from the provider into price_history."""
    from fin.models.price_history import PriceHistoryModel
    from fin.services.price_history_service import _fetch_from_provider

    engine, Session = _make_isolated_db()
    db = Session()

    from datetime import date as date_cls

    fake_rows = [
        {"date": "2022-01-03", "close": 100.0},
        {"date": "2022-01-04", "close": 101.0},
    ]

    class FakeProvider:
        def supports(self, sym):
            return True

        def fetch_history(self, sym, start, end):
            return fake_rows

    with patch(
        "fin.services.providers.build_default_providers", return_value=[FakeProvider()]
    ):
        _fetch_from_provider(db, "SPY", None, "2022-01-01", date_cls(2022, 1, 5))

    rows = db.query(PriceHistoryModel).filter(PriceHistoryModel.symbol == "SPY").all()
    assert len(rows) == 2
    db.close()
    engine.dispose()


def test_fetch_from_provider_no_provider():
    """_fetch_from_provider should warn and return when no provider supports the symbol."""
    from fin.services.price_history_service import _fetch_from_provider
    from datetime import date as date_cls

    engine, Session = _make_isolated_db()
    db = Session()
    with patch("fin.services.providers.build_default_providers", return_value=[]):
        _fetch_from_provider(db, "UNKNOWN", None, "2022-01-01", date_cls(2022, 1, 5))
    db.close()
    engine.dispose()


def test_fetch_symbol_fresh_cache_skips_provider():
    """fetch_symbol should not call provider when DB has a row for today."""
    from datetime import timezone
    from fin.models.price_history import PriceHistoryModel
    from fin.services.price_history_service import fetch_symbol

    engine, Session = _make_isolated_db()
    db = Session()
    today = __import__("datetime").datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db.add(PriceHistoryModel(symbol="SPY", date=today, close=500.0))
    db.commit()

    with patch("fin.services.price_history_service._fetch_from_provider") as mock_fp:
        result = fetch_symbol(db, "SPY", "2022-01-01")

    mock_fp.assert_not_called()
    assert any(r["date"] == today for r in result)
    db.close()
    engine.dispose()


# ── benchmark_history_service helpers ─────────────────────────────────────────


def test_code_to_yf_symbol():
    from fin.services.benchmark_history_service import _code_to_yf_symbol

    assert _code_to_yf_symbol("SPY") == "SPY"
    assert _code_to_yf_symbol("510300") == "510300.SS"


def test_trading_dates_empty_allocations():
    from fin.services.benchmark_history_service import _trading_dates

    scheme = {"allocations": []}
    result = _trading_dates(scheme, {}, "2022-01-01", "2022-12-31")
    assert result == []


def test_trading_dates_with_prices():
    from fin.services.benchmark_history_service import _trading_dates

    scheme = {"allocations": [{"symbol": "SPY"}, {"symbol": "TLT"}]}
    price_cache = {
        "SPY": [
            {"date": "2022-01-03", "close": 400.0},
            {"date": "2022-01-04", "close": 401.0},
        ],
        "TLT": [
            {"date": "2022-01-03", "close": 100.0},
            {"date": "2022-01-05", "close": 101.0},
        ],
    }
    result = _trading_dates(scheme, price_cache, "2022-01-01", "2022-12-31")
    assert result == ["2022-01-03"]  # only date present in both


def test_trading_dates_missing_symbol():
    from fin.services.benchmark_history_service import _trading_dates

    scheme = {"allocations": [{"symbol": "MISSING"}]}
    result = _trading_dates(scheme, {}, "2022-01-01", "2022-12-31")
    assert result == []


def test_fix_stale_snapshot_allocations_no_snaps():
    """Should be a no-op when no portfolio snapshots exist."""
    from fin.services.benchmark_history_service import _fix_stale_snapshot_allocations

    engine, Session = _make_isolated_db()
    db = Session()
    _fix_stale_snapshot_allocations(db, 999)  # should not raise
    db.close()
    engine.dispose()


def test_fix_stale_snapshot_allocations_fixes_stale():
    """Stale snapshot with alloc sum > 100 should be rescaled."""
    import json
    from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
    from fin.services.benchmark_history_service import _fix_stale_snapshot_allocations

    engine, Session = _make_isolated_db()
    db = Session()
    snap = BenchmarkCustomSchemeModel(
        account_id=1,
        name="Portfolio 2022-01-01",
        allocations_json=json.dumps([{"symbol": "SPY", "pct": 100.0}]),
        cash_pct=10.0,  # total = 110%, stale
        enabled=1,
        is_portfolio_snapshot=1,
    )
    db.add(snap)
    db.commit()
    _fix_stale_snapshot_allocations(db, 1)
    db.refresh(snap)
    allocs = json.loads(snap.allocations_json)
    assert sum(a["pct"] for a in allocs) + snap.cash_pct <= 100.1
    db.close()
    engine.dispose()


def test_get_or_create_portfolio_snapshot_creates_new():
    """A new snapshot should be created when none exists."""
    from fin.services.benchmark_history_service import _get_or_create_portfolio_snapshot

    engine, Session = _make_isolated_db()
    db = Session()
    portfolio_scheme = {
        "id": "__portfolio__",
        "name": "Portfolio",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    snap = _get_or_create_portfolio_snapshot(db, 1, portfolio_scheme, "2022-01-03")
    assert snap is not None
    assert snap.is_portfolio_snapshot == 1
    db.close()
    engine.dispose()


def test_get_or_create_portfolio_snapshot_reuses_recent():
    """A snapshot created less than interval_days ago should be reused."""
    from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
    from fin.services.benchmark_history_service import _get_or_create_portfolio_snapshot

    engine, Session = _make_isolated_db()
    db = Session()
    portfolio_scheme = {
        "id": "__portfolio__",
        "name": "Portfolio",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    snap1 = _get_or_create_portfolio_snapshot(
        db, 1, portfolio_scheme, "2022-01-03", interval_days=30
    )
    snap2 = _get_or_create_portfolio_snapshot(
        db, 1, portfolio_scheme, "2022-01-20", interval_days=30
    )
    assert snap1.id == snap2.id  # reused, not new
    count = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(BenchmarkCustomSchemeModel.account_id == 1)
        .count()
    )
    assert count == 1
    db.close()
    engine.dispose()


def test_build_backfill_price_cache_mocked():
    """_build_backfill_price_cache should fetch all symbols in schemes."""
    from fin.services.benchmark_history_service import _build_backfill_price_cache

    engine, Session = _make_isolated_db()
    db = Session()
    schemes = [{"allocations": [{"symbol": "SPY"}, {"symbol": "TLT"}]}]
    fake = [{"date": "2022-01-03", "close": 100.0}]
    with patch("fin.services.price_history_service.fetch_symbol", return_value=fake):
        cache = _build_backfill_price_cache(db, schemes, "2022-01-01")
    assert "SPY" in cache
    assert "TLT" in cache
    db.close()
    engine.dispose()


def test_backfill_scheme_dates_writes_rows():
    """_backfill_scheme_dates should write result rows for each trading date."""
    from datetime import datetime, timezone
    from fin.services.benchmark_history_service import _backfill_scheme_dates

    engine, Session = _make_isolated_db()
    db = Session()

    scheme = {
        "id": "sp500",
        "name": "S&P 500",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    income = [
        {
            "date": "2022-01-03",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        }
    ]
    price_cache = {
        "SPY": [
            {"date": "2022-01-03", "close": 100.0},
            {"date": "2022-07-01", "close": 110.0},
            {"date": "2023-01-02", "close": 120.0},
        ]
    }
    fx = {"USD": 7.2, "CNY": 1.0}
    existing: set = set()
    now_utc = datetime.now(timezone.utc)

    n = _backfill_scheme_dates(
        db,
        1,
        scheme,
        income,
        price_cache,
        fx,
        existing,
        now_utc,
        "2022-01-01",
        "2023-06-01",
    )
    assert n > 0
    db.close()
    engine.dispose()


def test_backfill_all_calls_backfill_account():
    """backfill_all should call backfill_account for every enabled account."""
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import backfill_all

    engine, Session = _make_isolated_db()
    db = Session()
    db.add(
        AccountModel(
            user_id=MOCK_USER_ID, name="Acc1", currency="USD", benchmark_enabled="1"
        )
    )
    db.add(
        AccountModel(
            user_id=MOCK_USER_ID, name="Acc2", currency="USD", benchmark_enabled="0"
        )
    )
    db.commit()

    with patch(
        "fin.services.benchmark_history_service.backfill_account", return_value=5
    ) as mock_bf:
        backfill_all(db)

    assert mock_bf.call_count == 1  # only 1 enabled account
    db.close()
    engine.dispose()


# ── benchmark_service coverage gaps ──────────────────────────────────────────


def test_load_benchmark_defaults_cache():
    """Second call should return the cached list without reading disk again."""
    import fin.services.benchmark_service as bsvc

    original = bsvc._DEFAULTS_CACHE
    try:
        bsvc._DEFAULTS_CACHE = [{"id": "cached", "name": "Cached"}]
        result = bsvc._load_benchmark_defaults()
        assert result[0]["id"] == "cached"
    finally:
        bsvc._DEFAULTS_CACHE = original


def test_resolve_schemes_json_decode_error():
    """_resolve_schemes should fall back to all defaults on json decode error."""
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import _resolve_schemes

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID,
        name="Acc",
        currency="USD",
        benchmark_enabled="1",
        benchmark_schemes="{bad json}",
    )
    db.add(account)
    db.commit()

    fake_defaults = [
        {
            "id": "sp500",
            "name": "S&P 500",
            "allocations": [{"symbol": "SPY", "pct": 100.0}],
            "cash_pct": 0.0,
        }
    ]
    with patch(
        "fin.services.benchmark_service._load_benchmark_defaults",
        return_value=fake_defaults,
    ):
        result = _resolve_schemes(db, account)
    assert any(s["id"] == "sp500" for s in result)
    db.close()
    engine.dispose()


def test_resolve_schemes_includes_custom():
    """_resolve_schemes should include custom schemes."""
    import json
    from fin.models.account import AccountModel
    from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import _resolve_schemes

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="Acc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    cs = BenchmarkCustomSchemeModel(
        account_id=account.id,
        name="My 60/40",
        allocations_json=json.dumps(
            [{"symbol": "SPY", "pct": 60.0}, {"symbol": "TLT", "pct": 40.0}]
        ),
        cash_pct=0.0,
        enabled=1,
        is_portfolio_snapshot=0,
    )
    db.add(cs)
    db.commit()

    with patch(
        "fin.services.benchmark_service._load_benchmark_defaults", return_value=[]
    ):
        result = _resolve_schemes(db, account)
    assert any(s["name"] == "My 60/40" for s in result)
    db.close()
    engine.dispose()


def test_has_recent_result_false_no_rows():
    """has_recent_result returns False when no portfolio result row exists."""
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import has_recent_result

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="Acc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.commit()
    assert has_recent_result(db, account.id) is False
    db.close()
    engine.dispose()


def test_fetch_fx_mocked():
    """_fetch_fx should return rates from QuoteService."""
    from fin.services.benchmark_service import _fetch_fx

    engine, Session = _make_isolated_db()
    db = Session()

    class FakeQS:
        def get_fx(self, pairs):
            return {"CNY": 1.0, "USD": 7.2, "HKD": 0.92}

    with (
        patch("fin.services.quote.QuoteService", return_value=FakeQS()),
        patch("fin.services.providers.build_default_providers", return_value=[]),
    ):
        rates = _fetch_fx(db)

    assert rates["USD"] == 7.2
    db.close()
    engine.dispose()


def test_fetch_current_price_mocked():
    """_fetch_current_price should return price from QuoteService."""
    from fin.services.benchmark_service import _fetch_current_price

    class FakeQS:
        def get_quote(self, sym):
            return {"price": 123.45}

    with (
        patch("fin.services.quote.QuoteService", return_value=FakeQS()),
        patch("fin.services.providers.build_default_providers", return_value=[]),
        patch("fin.database.SessionLocal"),
    ):
        price = _fetch_current_price("SPY")

    assert price == pytest.approx(123.45)


def test_holding_current_price_fallback():
    """_holding_current_price should fall back to last series entry."""
    from fin.services.benchmark_service import _holding_current_price

    engine, Session = _make_isolated_db()
    db = Session()
    series = [
        {"date": "2022-01-03", "close": 99.0},
        {"date": "2023-01-02", "close": 111.0},
    ]

    class FakeQS:
        def get_quote(self, sym):
            return None  # no price

    with (
        patch("fin.services.quote.QuoteService", return_value=FakeQS()),
        patch("fin.services.providers.build_default_providers", return_value=[]),
    ):
        price = _holding_current_price(db, "NVDA", series)

    assert price == 111.0
    db.close()
    engine.dispose()


def test_compute_account_not_found(benchmark_client):
    """compute() raises ValueError when account_id does not exist."""
    from fin.services.benchmark_service import compute

    engine, Session = _make_isolated_db()
    db = Session()
    import pytest

    with pytest.raises(ValueError, match="not found"):
        from fin.services.benchmark_service import compute

        compute(db, 99999)
    db.close()
    engine.dispose()


def test_compute_benchmark_disabled_raises(benchmark_client):
    """compute() raises ValueError when benchmark is disabled."""
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import compute

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="Acc", currency="USD", benchmark_enabled="0"
    )
    db.add(account)
    db.commit()

    with pytest.raises(ValueError, match="benchmark disabled"):
        compute(db, account.id)
    db.close()
    engine.dispose()


def test_compute_portfolio_xirr_with_income():
    """_compute_portfolio_xirr should produce a value when income + holdings exist."""
    from fin.models.account import AccountModel
    from fin.models.holding import HoldingModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import _compute_portfolio_xirr

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="Acc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    holding = HoldingModel(
        user_id=MOCK_USER_ID,
        account="Acc",
        code="SPY",
        shares=10.0,
        avg_cost=400.0,
        currency="USD",
        market="US",
    )
    db.add(holding)
    db.commit()

    income = [
        {
            "date": "2022-01-03",
            "amount": 1000.0,
            "currency": "USD",
            "category": "deposit",
        }
    ]
    price_cache: dict = {}
    fx = {"USD": 7.2, "CNY": 1.0}
    series = [
        {"date": "2022-01-03", "close": 400.0},
        {"date": "2024-01-02", "close": 500.0},
    ]

    with (
        patch(
            "fin.services.benchmark_service._holding_current_price", return_value=500.0
        ),
        patch("fin.services.benchmark_service.fetch_symbol", return_value=series),
    ):
        result_xirr, terminal = _compute_portfolio_xirr(
            db, account, income, fx, price_cache, "2022-01-01"
        )

    assert terminal > 0
    db.close()
    engine.dispose()


def test_compute_portfolio_snap_result_with_snapshot():
    """_compute_portfolio_snap_result should return a result dict when snapshot exists."""
    import json
    from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
    from fin.services.benchmark_service import _compute_portfolio_snap_result

    engine, Session = _make_isolated_db()
    db = Session()

    snap = BenchmarkCustomSchemeModel(
        account_id=1,
        name="Portfolio 2022-01-01",
        allocations_json=json.dumps([{"symbol": "SPY", "pct": 100.0}]),
        cash_pct=0.0,
        enabled=1,
        is_portfolio_snapshot=1,
    )
    db.add(snap)
    db.commit()

    income = [
        {
            "date": "2022-01-03",
            "amount": 1000.0,
            "currency": "USD",
            "category": "deposit",
        }
    ]
    price_cache: dict = {}
    current_prices: dict = {}
    fx = {"USD": 7.2, "CNY": 1.0}
    series = [
        {"date": "2022-01-03", "close": 400.0},
        {"date": "2024-01-02", "close": 500.0},
    ]

    with (
        patch("fin.services.benchmark_service.fetch_symbol", return_value=series),
        patch(
            "fin.services.benchmark_service._fetch_current_price", return_value=500.0
        ),
    ):
        result = _compute_portfolio_snap_result(
            db, 1, income, price_cache, current_prices, fx
        )

    assert result is not None
    assert "xirr" in result
    db.close()
    engine.dispose()


# ── has_recent_result positive path ──────────────────────────────────────────


def test_has_recent_result_true_with_portfolio_row():
    """has_recent_result returns True when all active scheme results are fresh."""
    from datetime import datetime, timezone
    from fin.models.account import AccountModel
    from fin.models.benchmark_result import BenchmarkResultModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import has_recent_result

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID,
        name="Acc",
        currency="USD",
        benchmark_enabled="1",
        benchmark_schemes='{"enabled_defaults": []}',
    )
    db.add(account)
    db.flush()
    today = str(datetime.now(timezone.utc).date())
    now_utc = datetime.now(timezone.utc)
    db.add(
        BenchmarkResultModel(
            account_id=account.id,
            bench_id="__portfolio__",
            computed_date=today,
            xirr=5.0,
            computed_at=now_utc,
        )
    )
    db.commit()

    with patch(
        "fin.services.benchmark_service._load_benchmark_defaults", return_value=[]
    ):
        result = has_recent_result(db, account.id)
    assert result is True
    db.close()
    engine.dispose()


def test_has_recent_result_false_missing_scheme():
    """has_recent_result returns False when an active scheme has no recent result."""
    from datetime import datetime, timezone
    from fin.models.account import AccountModel
    from fin.models.benchmark_result import BenchmarkResultModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import has_recent_result

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID,
        name="Acc2",
        currency="USD",
        benchmark_enabled="1",
    )
    db.add(account)
    db.flush()
    today = str(datetime.now(timezone.utc).date())
    now_utc = datetime.now(timezone.utc)
    db.add(
        BenchmarkResultModel(
            account_id=account.id,
            bench_id="__portfolio__",
            computed_date=today,
            xirr=5.0,
            computed_at=now_utc,
        )
    )
    db.commit()

    fake_scheme = {"id": "sp500", "name": "S&P 500", "allocations": [], "cash_pct": 0.0}
    with patch(
        "fin.services.benchmark_service._load_benchmark_defaults",
        return_value=[fake_scheme],
    ):
        result = has_recent_result(db, account.id)
    assert result is False
    db.close()
    engine.dispose()


# ── _fetch_current_price no-price path ────────────────────────────────────────


def test_fetch_current_price_no_price_returns_none():
    """_fetch_current_price returns None when quote has no price field."""
    from fin.services.benchmark_service import _fetch_current_price

    class FakeQS:
        def get_quote(self, sym):
            return {"name": "SPY"}  # no price key

    mock_db = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    with (
        patch("fin.services.quote.QuoteService", return_value=FakeQS()),
        patch("fin.services.providers.build_default_providers", return_value=[]),
        patch("fin.database.SessionLocal", return_value=mock_db),
    ):
        price = _fetch_current_price("SPY")
    assert price is None


# ── _holding_current_price edge cases ─────────────────────────────────────────


def test_holding_current_price_no_fallback_returns_none():
    """_holding_current_price returns None when QuoteService has no price and no series."""
    from fin.services.benchmark_service import _holding_current_price

    engine, Session = _make_isolated_db()
    db = Session()

    class FakeQS:
        def get_quote(self, sym):
            return None

    with (
        patch("fin.services.quote.QuoteService", return_value=FakeQS()),
        patch("fin.services.providers.build_default_providers", return_value=[]),
    ):
        price = _holding_current_price(db, "NVDA", [])

    assert price is None
    db.close()
    engine.dispose()


def test_holding_current_price_exception_uses_fallback():
    """_holding_current_price uses fallback series when QuoteService raises."""
    from fin.services.benchmark_service import _holding_current_price

    engine, Session = _make_isolated_db()
    db = Session()
    series = [{"date": "2022-01-03", "close": 99.0}]

    class RaisingQS:
        def get_quote(self, sym):
            raise RuntimeError("network error")

    with (
        patch("fin.services.quote.QuoteService", return_value=RaisingQS()),
        patch("fin.services.providers.build_default_providers", return_value=[]),
    ):
        price = _holding_current_price(db, "NVDA", series)

    assert price == 99.0
    db.close()
    engine.dispose()


# ── _compute_portfolio_xirr with CASH + withdrawal ────────────────────────────


def test_compute_portfolio_xirr_with_cash_holding():
    """_compute_portfolio_xirr handles CASH position (price = 1.0)."""
    from fin.models.account import AccountModel
    from fin.models.holding import HoldingModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_service import _compute_portfolio_xirr

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="Acc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    db.add(
        HoldingModel(
            user_id=MOCK_USER_ID,
            account="Acc",
            code="CASH",
            shares=500.0,
            avg_cost=1.0,
            currency="USD",
            market="cash",
        )
    )
    db.commit()

    income = [
        {
            "date": "2022-01-03",
            "amount": 1000.0,
            "currency": "USD",
            "category": "deposit",
        },
        {
            "date": "2022-06-01",
            "amount": 200.0,
            "currency": "USD",
            "category": "withdrawal",
        },
    ]
    fx = {"USD": 7.2, "CNY": 1.0}
    result_xirr, terminal = _compute_portfolio_xirr(
        db, account, income, fx, {}, "2022-01-01"
    )

    assert terminal > 0
    db.close()
    engine.dispose()


# ── _backfill_scheme_dates skip existing ─────────────────────────────────────


def test_backfill_scheme_dates_skips_existing():
    """_backfill_scheme_dates should skip (bench_id, date) pairs already in existing."""
    from datetime import datetime, timezone
    from fin.services.benchmark_history_service import _backfill_scheme_dates

    engine, Session = _make_isolated_db()
    db = Session()

    scheme = {
        "id": "sp500",
        "name": "S&P 500",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    price_cache = {
        "SPY": [
            {"date": "2022-01-03", "close": 100.0},
            {"date": "2022-07-01", "close": 110.0},
            {"date": "2023-01-02", "close": 120.0},
        ]
    }
    income = [
        {
            "date": "2022-01-03",
            "currency": "USD",
            "amount": 1000.0,
            "category": "deposit",
        }
    ]
    fx = {"USD": 7.2, "CNY": 1.0}
    # Pre-populate existing with all possible dates
    existing = {
        ("sp500", "2022-01-03"),
        ("sp500", "2022-07-01"),
        ("sp500", "2023-01-02"),
    }
    now_utc = datetime.now(timezone.utc)

    n = _backfill_scheme_dates(
        db,
        1,
        scheme,
        income,
        price_cache,
        fx,
        existing,
        now_utc,
        "2022-01-01",
        "2023-06-01",
    )
    assert n == 0  # all skipped
    db.close()
    engine.dispose()


# ── backfill_all exception path ───────────────────────────────────────────────


def test_backfill_all_handles_exception():
    """backfill_all should continue to next account when one raises."""
    from fin.models.account import AccountModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import backfill_all

    engine, Session = _make_isolated_db()
    db = Session()
    db.add(
        AccountModel(
            user_id=MOCK_USER_ID, name="BFExc", currency="USD", benchmark_enabled="1"
        )
    )
    db.commit()

    with patch("fin.services.benchmark_history_service.logger") as mock_log:
        with patch(
            "fin.services.benchmark_history_service.backfill_account",
            side_effect=RuntimeError("fail"),
        ):
            backfill_all(db)  # should not raise

    mock_log.exception.assert_called_once()
    assert "Backfill failed" in mock_log.exception.call_args[0][0]
    db.close()
    engine.dispose()


# ── _fetch_price_data fallback to series close ─────────────────────────────────


def test_fetch_price_data_live_none_falls_back_to_series():
    """When live price is None, falls back to last entry in price_cache series."""
    from fin.services.benchmark_service import _fetch_price_data

    fake_series = [{"date": "2022-01-03", "close": 99.0}]
    with (
        patch("fin.services.benchmark_service.fetch_symbol", return_value=fake_series),
        patch("fin.services.benchmark_service._fetch_current_price", return_value=None),
    ):
        cache, prices = _fetch_price_data(["SPY"], "2022-01-01")

    assert prices.get("SPY") == 99.0  # fallback to series[-1]["close"]


# ── backfill_account edge paths ───────────────────────────────────────────────


def test_backfill_account_future_income_returns_zero():
    """backfill_account returns 0 when all income is in the future (yesterday < earliest)."""
    from fin.models.account import AccountModel
    from fin.models.income import IncomeModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import backfill_account

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="FutureAcc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    # Deposit in the distant future
    db.add(
        IncomeModel(
            user_id=MOCK_USER_ID,
            date="2099-01-01",
            source="dep",
            category="deposit",
            amount=1000.0,
            currency="USD",
            account="FutureAcc",
        )
    )
    db.commit()

    with patch(
        "fin.services.benchmark_service._fetch_fx",
        return_value={"USD": 7.2, "CNY": 1.0},
    ):
        result = backfill_account(db, account.id)

    assert result == 0
    db.close()
    engine.dispose()


def test_backfill_account_config_read_error_uses_default():
    """backfill_account falls back to snapshot_interval=30 when app.json can't be read."""
    from fin.models.account import AccountModel
    from fin.models.income import IncomeModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import backfill_account

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="CfgErrAcc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    db.add(
        IncomeModel(
            user_id=MOCK_USER_ID,
            date="2022-01-03",
            source="dep",
            category="deposit",
            amount=1000.0,
            currency="USD",
            account="CfgErrAcc",
        )
    )
    db.commit()

    fake_scheme = {
        "id": "sp500",
        "name": "S&P 500",
        "allocations": [{"symbol": "SPY", "pct": 100.0}],
        "cash_pct": 0.0,
    }
    fake_series = [
        {"date": "2022-01-03", "close": 100.0},
        {"date": "2022-07-01", "close": 110.0},
        {"date": "2023-01-02", "close": 120.0},
    ]

    with (
        patch(
            "fin.services.benchmark_service._load_benchmark_defaults",
            return_value=[fake_scheme],
        ),
        patch(
            "fin.services.benchmark_history_service._build_backfill_price_cache",
            return_value={"SPY": fake_series},
        ),
        patch(
            "fin.services.benchmark_service._fetch_fx",
            return_value={"USD": 7.2, "CNY": 1.0},
        ),
        patch(
            "fin.services.benchmark_history_service._build_portfolio_scheme",
            return_value=None,
        ),
        patch("fin.config.APP_CONFIG_PATH") as mock_path,
    ):
        mock_path.read_text.side_effect = OSError("config not found")
        n = backfill_account(db, account.id)

    assert n >= 0  # completes without raising
    db.close()
    engine.dispose()


def test_build_backfill_price_cache_error_handled():
    """_build_backfill_price_cache logs warning and stores empty list on error."""
    from fin.services.benchmark_history_service import _build_backfill_price_cache

    engine, Session = _make_isolated_db()
    db = Session()
    schemes = [{"allocations": [{"symbol": "BROKEN"}]}]

    with patch(
        "fin.services.price_history_service.fetch_symbol",
        side_effect=RuntimeError("boom"),
    ):
        cache = _build_backfill_price_cache(db, schemes, "2022-01-01")

    assert cache["BROKEN"] == []
    db.close()
    engine.dispose()


def test_build_portfolio_scheme_with_holdings():
    """_build_portfolio_scheme returns a scheme dict when holdings are present."""
    from fin.models.account import AccountModel
    from fin.models.holding import HoldingModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import _build_portfolio_scheme

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="PfAcc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    holding = HoldingModel(
        user_id=MOCK_USER_ID,
        account="PfAcc",
        code="SPY",
        shares=10.0,
        avg_cost=400.0,
        currency="USD",
        market="US",
    )
    db.add(holding)
    db.commit()

    price_cache = {"SPY": [{"date": "2022-01-03", "close": 400.0}]}
    fx = {"USD": 7.2, "CNY": 1.0}

    with patch(
        "fin.services.benchmark_service._holding_current_price", return_value=400.0
    ):
        result = _build_portfolio_scheme(db, account, fx, price_cache)

    assert result is not None
    assert result["id"] == "__portfolio__"
    assert len(result["allocations"]) >= 1
    db.close()
    engine.dispose()


def test_collect_portfolio_snapshot_schemes_with_snaps():
    """_collect_portfolio_snapshot_schemes returns existing snapshots."""
    import json
    from fin.models.account import AccountModel
    from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
    from fin.models.user import MOCK_USER_ID
    from fin.services.benchmark_history_service import (
        _collect_portfolio_snapshot_schemes,
    )

    engine, Session = _make_isolated_db()
    db = Session()
    account = AccountModel(
        user_id=MOCK_USER_ID, name="SnapAcc", currency="USD", benchmark_enabled="1"
    )
    db.add(account)
    db.flush()
    snap = BenchmarkCustomSchemeModel(
        account_id=account.id,
        name="Portfolio 2022-01-01",
        allocations_json=json.dumps([{"symbol": "SPY", "pct": 100.0}]),
        cash_pct=0.0,
        enabled=1,
        is_portfolio_snapshot=1,
    )
    db.add(snap)
    db.commit()

    base_schemes = [
        {
            "id": "sp500",
            "name": "S&P 500",
            "allocations": [{"symbol": "SPY", "pct": 100.0}],
            "cash_pct": 0.0,
        }
    ]
    price_cache: dict = {"SPY": [{"date": "2022-01-03", "close": 400.0}]}
    fx = {"USD": 7.2, "CNY": 1.0}

    with patch(
        "fin.services.benchmark_history_service._build_portfolio_scheme",
        return_value=None,
    ):
        result = _collect_portfolio_snapshot_schemes(
            db, account, fx, price_cache, base_schemes, "2026-06-03", 30, "2022-01-01"
        )

    assert len(result) > len(base_schemes)  # includes the snapshot
    assert any(str(snap.id) == s["id"] for s in result)
    db.close()
    engine.dispose()
