"""Regression tests for the dev/prod environment guard.

Two layers under test:
1. fin/config.py FIN_DEV hard-pin — when --dev is on, env overrides
   (FIN_DB_PATH, FIN_PORT) MUST be ignored so a stale shell export can't
   silently route the dev server at prod data.
2. Skill _resolve_base() — when ~/.fin-dev or <repo>/.dev-machine is
   present, prod URLs MUST be refused unless FIN_ALLOW_PROD=1.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

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


# ── Layer 2: skill _resolve_base guard ───────────────────────────────────────


def _reload_post_bulk():
    """Re-import post_bulk so env / marker changes take effect."""
    if "post_bulk" in sys.modules:
        importlib.reload(sys.modules["post_bulk"])
    import post_bulk

    return post_bulk


def test_no_markers_no_guard(monkeypatch, tmp_path):
    """Normal user: no markers anywhere → skill writes go through."""
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.fin-dev
    monkeypatch.delenv("FIN_API_URL", raising=False)
    monkeypatch.delenv("FIN_ALLOW_PROD", raising=False)
    # Move repo-level .dev-machine aside for the test
    marker = REPO_ROOT / ".dev-machine"
    backup = REPO_ROOT / ".dev-machine.testbackup"
    marker_existed = marker.exists()
    if marker_existed:
        marker.rename(backup)
    try:
        pb = _reload_post_bulk()
        assert pb._is_dev_machine() is False
        assert pb._resolve_base() == "http://localhost:8899"
    finally:
        if marker_existed:
            backup.rename(marker)


def test_home_marker_triggers_guard(monkeypatch, tmp_path):
    """~/.fin-dev alone triggers refusal."""
    (tmp_path / ".fin-dev").touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIN_API_URL", raising=False)
    monkeypatch.delenv("FIN_ALLOW_PROD", raising=False)
    pb = _reload_post_bulk()
    assert pb._is_dev_machine() is True
    import pytest

    with pytest.raises(SystemExit, match="REFUSED"):
        pb._resolve_base()


def test_repo_marker_triggers_guard_even_without_home_marker(monkeypatch, tmp_path):
    """Defense in depth: rm'ing ~/.fin-dev doesn't disable protection if
    <repo>/.dev-machine still exists."""
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.fin-dev
    monkeypatch.delenv("FIN_API_URL", raising=False)
    monkeypatch.delenv("FIN_ALLOW_PROD", raising=False)
    marker = REPO_ROOT / ".dev-machine"
    marker_existed = marker.exists()
    if not marker_existed:
        marker.touch()
    try:
        pb = _reload_post_bulk()
        assert pb._is_dev_machine() is True
        import pytest

        with pytest.raises(SystemExit, match="REFUSED"):
            pb._resolve_base()
    finally:
        if not marker_existed:
            marker.unlink()


def test_dev_url_passes_through(monkeypatch, tmp_path):
    """Dev machine + dev URL (18899) → no refusal."""
    (tmp_path / ".fin-dev").touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FIN_API_URL", "http://127.0.0.1:18899")
    monkeypatch.delenv("FIN_ALLOW_PROD", raising=False)
    pb = _reload_post_bulk()
    assert pb._resolve_base() == "http://127.0.0.1:18899"


def test_allow_prod_escape_hatch(monkeypatch, tmp_path):
    """FIN_ALLOW_PROD=1 is the ONLY way to write prod from a dev machine."""
    (tmp_path / ".fin-dev").touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIN_API_URL", raising=False)
    monkeypatch.setenv("FIN_ALLOW_PROD", "1")
    pb = _reload_post_bulk()
    assert pb._resolve_base() == "http://localhost:8899"
