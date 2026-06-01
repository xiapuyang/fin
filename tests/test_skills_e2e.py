"""End-to-end tests for fin-import + fin-accounts skill scripts.

Spawns a real uvicorn server as a subprocess on a free port, pointed at a
throwaway SQLite DB via the FIN_DB_PATH env override (added in fin/config.py).
Skill scripts hit it through FIN_API_URL exactly the way a user invocation
would.

Why subprocess (not threading)
------------------------------
Threading-based fixtures can't relocate the SQLAlchemy engine after other
tests have already imported fin.models.* against the original Base. A fresh
subprocess gets a clean import graph, reads FIN_DB_PATH at import time, and
binds models to the correct engine.

Marked with @pytest.mark.e2e so they can be opt-in:
    uv run pytest -m e2e --no-cov

The default `uv run pytest` collection skips them via the marker filter in
pyproject.toml addopts. To include them in CI: `uv run pytest -m "e2e or not e2e"`.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).parent.parent
SKILLS = REPO_ROOT / "skills"
sys.path.insert(0, str(SKILLS / "fin-import" / "scripts"))
sys.path.insert(0, str(SKILLS / "fin-accounts" / "scripts"))


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(base: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(base + "/api/health", timeout=0.5)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"server at {base} never became healthy")


@pytest.fixture(scope="module")
def fin_server(tmp_path_factory):
    """Spawn uvicorn in a subprocess with a throwaway SQLite DB."""
    db_path = tmp_path_factory.mktemp("fin_e2e") / "test.db"
    port = _find_free_port()

    env = os.environ.copy()
    env["FIN_DB_PATH"] = str(db_path)

    # Inline runner: imports the app fresh, init_db creates the schema, uvicorn
    # serves it. Easier to manage than `uv run python serve.py` since serve.py
    # hardcodes 8888 and includes the price updater + scheduler we don't need.
    runner = (
        "from fin.api import app; "
        "from fin.database import init_db; init_db(); "
        f"import uvicorn; uvicorn.run(app, host='127.0.0.1', port={port}, log_level='warning')"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", runner],
        env=env,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
    except Exception:
        proc.terminate()
        try:
            out, err = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        raise RuntimeError(
            f"server failed to start. stdout={out.decode()[:500]} stderr={err.decode()[:500]}"
        )

    os.environ["FIN_API_URL"] = base
    yield base

    os.environ.pop("FIN_API_URL", None)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ── fin-import: post → preview → re-post round trip ──────────────────────────


@pytest.mark.e2e
def test_alerts_bulk_e2e_roundtrip(fin_server):
    """Full path: POST 2 alerts → preview shows 0 new / 2 skip → POST returns
    created=0, skipped=2.  Validates server dedup AND skill client-side dedup
    agree on the same natural-key set."""
    from post_bulk import post
    from preview import dedup

    rows = [
        {"symbol": "NVDA", "name": "Nvidia", "condition": "price_gte", "value": 500.0},
        {"symbol": "META", "name": "Meta", "condition": "price_lte", "value": 400.0},
    ]

    first = post("alerts", rows)
    assert first["created"] == 2
    assert first["skipped"] == 0
    assert first["errors"] == []

    existing = requests.get(fin_server + "/api/alerts").json()
    # Alerts API returns `code` not `symbol`; preview dedup expects schema-shaped
    # rows with `symbol`. Adapt for the test by remapping.
    existing_for_dedup = [
        {"symbol": a["code"], "condition": a["cond"], "value": a["threshold"]}
        for a in existing
    ]
    new, skipped = dedup("alerts", rows, existing_for_dedup)
    assert len(new) == 0
    assert skipped == 2

    second = post("alerts", rows)
    assert second["created"] == 0
    assert second["skipped"] == 2


@pytest.mark.e2e
def test_holdings_with_default_account_injection_e2e(fin_server):
    """Simulates the AUQ flow: user picks 'IBKR' as the import account → all
    rows get stamped with account='IBKR' → POST succeeds."""
    from post_bulk import post
    from transform import TEMPLATES_DIR, transform

    template = json.loads((TEMPLATES_DIR / "holdings.json").read_text())
    raw_rows = [
        {"code": "AAPL", "market": "US", "shares": "50", "avg_cost": "150"},
        {"code": "TSLA", "market": "US", "shares": "25", "avg_cost": "180"},
    ]
    result = transform(raw_rows, template, default_account="IBKR")
    assert all(r["account"] == "IBKR" for r in result.rows)

    response = post("holdings", result.rows)
    assert response["created"] == 2
    assert response["errors"] == []

    listed = requests.get(fin_server + "/api/holdings").json()
    assert {h["code"] for h in listed} == {"AAPL", "TSLA"}
    assert all(h["account"] == "IBKR" for h in listed)


# ── fin-accounts: end-to-end ─────────────────────────────────────────────────


@pytest.mark.e2e
def test_accounts_bulk_e2e_with_parent_resolution(fin_server):
    """Mixed roots + children in one batch; server resolves parent_name → id."""
    from parse_accounts import parse_text
    from setup_accounts import post

    rows = parse_text("IB/股票账户\nIB/现金\n汇丰银行 > 活期")
    response = post(rows)
    assert response["created"] == 5  # 2 roots + 3 children
    assert response["errors"] == []

    accts = requests.get(fin_server + "/api/balance/accounts").json()
    by_name = {a["name"]: a for a in accts}
    assert by_name["股票账户"]["parent_id"] == by_name["IB"]["id"]
    assert by_name["活期"]["parent_id"] == by_name["汇丰银行"]["id"]


@pytest.mark.e2e
def test_accounts_bulk_unknown_parent_rejected(fin_server):
    """Server returns 400 with the missing parent name; payload dumped to /tmp."""
    from setup_accounts import post

    response = post([{"name": "Orphan", "parent_name": "NonExistentParent"}])
    assert response["created"] == 0
    assert response["errors"]
    assert "NonExistentParent" in response["errors"][0]["reason"]
