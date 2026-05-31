"""Regression tests for the dev/prod environment guard.

Two layers under test:
1. fin/config.py FIN_DEV hard-pin — when --dev is on, env overrides
   (FIN_DB_PATH, FIN_PORT) MUST be ignored so a stale shell export can't
   silently route the dev server at prod data.
2. Skill _resolve_base() — if BOTH the prod (8899) and dev (18899) fin
   servers are reachable, refuse. Otherwise honor FIN_API_URL or default.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "skills" / "fin-import" / "scripts"))


def _config_in_subprocess(env: dict[str, str]) -> dict[str, str]:
    """Read fin.config in a clean subprocess with the given env. Returns the
    resolved values as strings — subprocess isolates module-level FIN_DEV that
    config.py reads at import time."""
    code = (
        "from fin.config import API_PORT, DATA_DIR, DB_PATH;"
        "print(f'port={API_PORT}');"
        "print(f'data={DATA_DIR.name}');"
        "print(f'db={DB_PATH}')"
    )
    full_env = {**os.environ, **env}
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=full_env,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    out = {}
    for line in result.stdout.strip().splitlines():
        k, _, v = line.partition("=")
        out[k] = v
    return out


# ── Layer 1: config.py hard-pin ──────────────────────────────────────────────


def test_dev_mode_ignores_fin_db_path():
    """FIN_DEV=1 + FIN_DB_PATH set → FIN_DB_PATH must be ignored."""
    out = _config_in_subprocess(
        {"FIN_DEV": "1", "FIN_DB_PATH": "/tmp/should-be-ignored.db"}
    )
    assert out["data"] == "data-dev"
    assert out["db"].endswith("data-dev/fin.db")
    assert "should-be-ignored" not in out["db"]


def test_dev_mode_ignores_fin_port():
    """FIN_DEV=1 + FIN_PORT=8899 → port must stay 18899."""
    out = _config_in_subprocess({"FIN_DEV": "1", "FIN_PORT": "8899"})
    assert out["port"] == "18899"


def test_prod_mode_honors_fin_db_path():
    """Without FIN_DEV, FIN_DB_PATH override works (e2e tests rely on this)."""
    out = _config_in_subprocess({"FIN_DB_PATH": "/tmp/prod-override.db"})
    assert out["data"] == "data"
    assert out["db"] == "/tmp/prod-override.db"


def test_prod_mode_honors_fin_port():
    out = _config_in_subprocess({"FIN_PORT": "9000"})
    assert out["port"] == "9000"


# ── Layer 2: skill _resolve_base port-conflict guard ─────────────────────────


def _reload_post_bulk():
    """Re-import post_bulk so env changes take effect."""
    if "post_bulk" in sys.modules:
        importlib.reload(sys.modules["post_bulk"])
    import post_bulk

    return post_bulk


def test_no_servers_returns_default(monkeypatch):
    """Both ports closed → default URL returned (request will fail later)."""
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: False)
    assert pb._resolve_base() == "http://localhost:8899"


def test_only_prod_returns_default(monkeypatch):
    """Normal user: only prod up → use prod."""
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: port == pb.PROD_PORT)
    assert pb._resolve_base() == "http://localhost:8899"


def test_only_dev_honors_fin_api_url(monkeypatch):
    """Only dev up + explicit FIN_API_URL → use dev URL."""
    monkeypatch.setenv("FIN_API_URL", "http://127.0.0.1:18899")
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: port == pb.DEV_PORT)
    assert pb._resolve_base() == "http://127.0.0.1:18899"


def test_both_servers_refused(monkeypatch):
    """Both ports open → REFUSED, no override."""
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: True)
    with pytest.raises(SystemExit, match="REFUSED"):
        pb._resolve_base()
