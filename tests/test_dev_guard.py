"""Regression tests for the dev/prod environment guard.

Two layers under test:
1. fin/config.py FIN_DEV hard-pin — when --dev is on, env overrides
   (FIN_DB_PATH, FIN_PORT) MUST be ignored so a stale shell export can't
   silently route the dev server at prod data.
2. Skill _resolve_base() three-rule decision tree:
   a. ~/.fin-dev present → default to dev (18899), no port probe.
   b. No marker + both ports live → REFUSED (ambiguous target).
   c. Otherwise → FIN_API_URL or default localhost:8899.
   FIN_API_URL always wins when set.
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


def test_marker_forces_dev(monkeypatch, tmp_path):
    """~/.fin-dev present → default to dev URL, no port probe needed."""
    (tmp_path / ".fin-dev").touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    assert pb._resolve_base() == "http://127.0.0.1:18899"


def test_marker_skips_port_conflict_check(monkeypatch, tmp_path):
    """With marker, both servers running is fine — skill still goes to dev."""
    (tmp_path / ".fin-dev").touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: True)
    assert pb._resolve_base() == "http://127.0.0.1:18899"


def test_marker_honors_fin_api_url(monkeypatch, tmp_path):
    """Explicit FIN_API_URL wins even when marker is present."""
    (tmp_path / ".fin-dev").touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FIN_API_URL", "http://localhost:8899")
    pb = _reload_post_bulk()
    assert pb._resolve_base() == "http://localhost:8899"


def test_no_marker_no_servers_returns_default(monkeypatch, tmp_path):
    """Both ports closed → default URL (request will fail later)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: False)
    assert pb._resolve_base() == "http://localhost:8899"


def test_no_marker_only_prod_returns_default(monkeypatch, tmp_path):
    """Normal user: no marker, only prod up → use prod."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: port == pb.PROD_PORT)
    assert pb._resolve_base() == "http://localhost:8899"


def test_no_marker_only_dev_honors_fin_api_url(monkeypatch, tmp_path):
    """No marker, only dev up + explicit FIN_API_URL → use the URL."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FIN_API_URL", "http://127.0.0.1:18899")
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: port == pb.DEV_PORT)
    assert pb._resolve_base() == "http://127.0.0.1:18899"


def test_no_marker_both_servers_refused(monkeypatch, tmp_path):
    """No marker + both ports open → REFUSED, no override."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIN_API_URL", raising=False)
    pb = _reload_post_bulk()
    monkeypatch.setattr(pb, "_port_open", lambda port: True)
    with pytest.raises(SystemExit, match="REFUSED"):
        pb._resolve_base()
