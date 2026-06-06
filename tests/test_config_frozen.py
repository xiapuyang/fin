"""Tests for config.py path resolution across all platform/install-mode combinations.

Scenarios covered:
  Script mode  × macOS/Linux  × defaults / FIN_DEV / FIN_DATA_DIR / FIN_LOG_DIR / FIN_DB_PATH
  Script mode  × Windows      × defaults / FIN_DEV / FIN_DATA_DIR / FIN_LOG_DIR
  Frozen mode  × macOS/Linux  × defaults / FIN_DATA_DIR / FIN_LOG_DIR
  Frozen mode  × Windows      × defaults / FIN_DATA_DIR / FIN_LOG_DIR
"""

import importlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

_HOME_FIN = Path.home() / ".fin"


@contextmanager
def _config_context(
    *,
    frozen: bool = False,
    win32: bool = False,
    meipass: str | None = None,
    env: dict | None = None,
    win_data: Path | None = None,
    win_logs: Path | None = None,
):
    """Reload fin.config with patched state; yield a snapshot dict; restore on exit.

    win_data / win_logs are required when win32=True so mkdir() succeeds on macOS.
    """
    import fin.config as cfg

    _MISSING = object()
    orig_frozen = getattr(sys, "frozen", _MISSING)
    orig_meipass = getattr(sys, "_MEIPASS", _MISSING)
    orig_platform = sys.platform
    _ENV_KEYS = ("FIN_DATA_DIR", "FIN_LOG_DIR", "FIN_DEV", "FIN_DB_PATH")
    saved_env = {k: os.environ.get(k) for k in _ENV_KEYS}

    try:
        sys.platform = "win32" if win32 else "darwin"

        if frozen:
            sys.frozen = True
            sys._MEIPASS = meipass or "/fake/meipass"
        else:
            for attr in ("frozen", "_MEIPASS"):
                if hasattr(sys, attr):
                    delattr(sys, attr)

        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        for k, v in (env or {}).items():
            os.environ[k] = v

        if win32:
            assert win_data is not None and win_logs is not None, (
                "win_data and win_logs are required for win32=True tests"
            )
            with (
                patch("platformdirs.user_data_dir", return_value=str(win_data)),
                patch("platformdirs.user_log_dir", return_value=str(win_logs)),
            ):
                importlib.reload(cfg)
                yield _snapshot(cfg)
        else:
            importlib.reload(cfg)
            yield _snapshot(cfg)

    finally:
        sys.platform = orig_platform

        if orig_frozen is _MISSING:
            if hasattr(sys, "frozen"):
                delattr(sys, "frozen")
        else:
            sys.frozen = orig_frozen

        if orig_meipass is _MISSING:
            if hasattr(sys, "_MEIPASS"):
                delattr(sys, "_MEIPASS")
        else:
            sys._MEIPASS = orig_meipass

        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

        importlib.reload(cfg)


def _snapshot(cfg) -> dict:
    return {
        "DATA_DIR": cfg.DATA_DIR,
        "LOG_DIR": cfg.LOG_DIR,
        "DB_PATH": cfg.DB_PATH,
        "FIN_DEV": cfg.FIN_DEV,
    }


# ── Script mode · macOS/Linux ─────────────────────────────────────────────────


class TestScriptMacOS:
    def test_data_dir_default(self):
        with _config_context() as s:
            assert s["DATA_DIR"] == _HOME_FIN / "data"

    def test_log_dir_default(self):
        with _config_context() as s:
            assert s["LOG_DIR"] == _HOME_FIN / "logs"

    def test_db_path_default(self):
        with _config_context() as s:
            assert s["DB_PATH"] == _HOME_FIN / "data" / "fin.db"

    def test_fin_dev_false_by_default(self):
        with _config_context() as s:
            assert s["FIN_DEV"] is False

    def test_fin_dev_redirects_data_dir(self):
        with _config_context(env={"FIN_DEV": "1"}) as s:
            assert s["DATA_DIR"] == _HOME_FIN / "data-dev"
            assert s["FIN_DEV"] is True

    def test_fin_dev_does_not_change_log_dir(self):
        with _config_context(env={"FIN_DEV": "1"}) as s:
            assert s["LOG_DIR"] == _HOME_FIN / "logs"

    def test_fin_data_dir_override(self, tmp_path):
        with _config_context(env={"FIN_DATA_DIR": str(tmp_path)}) as s:
            assert s["DATA_DIR"] == tmp_path
            assert s["DB_PATH"] == tmp_path / "fin.db"

    def test_fin_data_dir_override_takes_precedence_over_fin_dev(self, tmp_path):
        with _config_context(env={"FIN_DEV": "1", "FIN_DATA_DIR": str(tmp_path)}) as s:
            assert s["DATA_DIR"] == tmp_path

    def test_fin_log_dir_override(self, tmp_path):
        with _config_context(env={"FIN_LOG_DIR": str(tmp_path)}) as s:
            assert s["LOG_DIR"] == tmp_path

    def test_fin_db_path_override(self, tmp_path):
        db = str(tmp_path / "custom.db")
        with _config_context(env={"FIN_DB_PATH": db}) as s:
            assert s["DB_PATH"] == Path(db)

    def test_fin_db_path_ignored_in_dev_mode(self, tmp_path):
        db = str(tmp_path / "custom.db")
        with _config_context(env={"FIN_DEV": "1", "FIN_DB_PATH": db}) as s:
            assert s["DB_PATH"] == _HOME_FIN / "data-dev" / "fin.db"


# ── Script mode · Windows ─────────────────────────────────────────────────────


class TestScriptWindows:
    def test_data_dir_default(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(win32=True, win_data=wd, win_logs=wl) as s:
            assert s["DATA_DIR"] == wd

    def test_log_dir_default(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(win32=True, win_data=wd, win_logs=wl) as s:
            assert s["LOG_DIR"] == wl

    def test_db_path_default(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(win32=True, win_data=wd, win_logs=wl) as s:
            assert s["DB_PATH"] == wd / "fin.db"

    def test_fin_dev_appends_data_dev(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(
            win32=True, win_data=wd, win_logs=wl, env={"FIN_DEV": "1"}
        ) as s:
            assert s["DATA_DIR"] == wd / "data-dev"

    def test_fin_data_dir_override(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        custom = tmp_path / "custom"
        with _config_context(
            win32=True, win_data=wd, win_logs=wl, env={"FIN_DATA_DIR": str(custom)}
        ) as s:
            assert s["DATA_DIR"] == custom

    def test_fin_log_dir_override(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        custom = tmp_path / "custom-logs"
        with _config_context(
            win32=True, win_data=wd, win_logs=wl, env={"FIN_LOG_DIR": str(custom)}
        ) as s:
            assert s["LOG_DIR"] == custom

    def test_not_under_home_fin(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(win32=True, win_data=wd, win_logs=wl) as s:
            assert not str(s["DATA_DIR"]).startswith(str(_HOME_FIN))


# ── Frozen mode · macOS/Linux ─────────────────────────────────────────────────


class TestFrozenMacOS:
    def test_data_dir_default(self, tmp_path):
        with _config_context(frozen=True, meipass=str(tmp_path / "bundle")) as s:
            assert s["DATA_DIR"] == _HOME_FIN / "data"

    def test_log_dir_default(self, tmp_path):
        with _config_context(frozen=True, meipass=str(tmp_path / "bundle")) as s:
            assert s["LOG_DIR"] == _HOME_FIN / "logs"

    def test_db_path_default(self, tmp_path):
        with _config_context(frozen=True, meipass=str(tmp_path / "bundle")) as s:
            assert s["DB_PATH"] == _HOME_FIN / "data" / "fin.db"

    def test_fin_dev_always_false(self, tmp_path):
        with _config_context(frozen=True, meipass=str(tmp_path / "bundle")) as s:
            assert s["FIN_DEV"] is False

    def test_data_not_inside_bundle(self, tmp_path):
        bundle = tmp_path / "bundle"
        with _config_context(frozen=True, meipass=str(bundle)) as s:
            assert not str(s["DATA_DIR"]).startswith(str(bundle))

    def test_fin_data_dir_override(self, tmp_path):
        custom = tmp_path / "custom"
        with _config_context(
            frozen=True,
            meipass=str(tmp_path / "bundle"),
            env={"FIN_DATA_DIR": str(custom)},
        ) as s:
            assert s["DATA_DIR"] == custom
            assert s["DB_PATH"] == custom / "fin.db"

    def test_fin_log_dir_override(self, tmp_path):
        custom = tmp_path / "custom-logs"
        with _config_context(
            frozen=True,
            meipass=str(tmp_path / "bundle"),
            env={"FIN_LOG_DIR": str(custom)},
        ) as s:
            assert s["LOG_DIR"] == custom


# ── Frozen mode · Windows ─────────────────────────────────────────────────────


class TestFrozenWindows:
    def test_data_dir_default(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(
            frozen=True,
            win32=True,
            meipass=str(tmp_path / "bundle"),
            win_data=wd,
            win_logs=wl,
        ) as s:
            assert s["DATA_DIR"] == wd

    def test_log_dir_default(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(
            frozen=True,
            win32=True,
            meipass=str(tmp_path / "bundle"),
            win_data=wd,
            win_logs=wl,
        ) as s:
            assert s["LOG_DIR"] == wl

    def test_db_path_default(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(
            frozen=True,
            win32=True,
            meipass=str(tmp_path / "bundle"),
            win_data=wd,
            win_logs=wl,
        ) as s:
            assert s["DB_PATH"] == wd / "fin.db"

    def test_fin_dev_always_false(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(
            frozen=True,
            win32=True,
            meipass=str(tmp_path / "bundle"),
            win_data=wd,
            win_logs=wl,
        ) as s:
            assert s["FIN_DEV"] is False

    def test_data_not_inside_bundle(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        bundle = tmp_path / "bundle"
        with _config_context(
            frozen=True, win32=True, meipass=str(bundle), win_data=wd, win_logs=wl
        ) as s:
            assert not str(s["DATA_DIR"]).startswith(str(bundle))

    def test_not_under_home_fin(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        with _config_context(
            frozen=True,
            win32=True,
            meipass=str(tmp_path / "bundle"),
            win_data=wd,
            win_logs=wl,
        ) as s:
            assert not str(s["DATA_DIR"]).startswith(str(_HOME_FIN))

    def test_fin_data_dir_override(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        custom = tmp_path / "custom"
        with _config_context(
            frozen=True,
            win32=True,
            meipass=str(tmp_path / "bundle"),
            win_data=wd,
            win_logs=wl,
            env={"FIN_DATA_DIR": str(custom)},
        ) as s:
            assert s["DATA_DIR"] == custom
            assert s["DB_PATH"] == custom / "fin.db"

    def test_fin_log_dir_override(self, tmp_path):
        wd, wl = tmp_path / "data", tmp_path / "logs"
        custom = tmp_path / "custom-logs"
        with _config_context(
            frozen=True,
            win32=True,
            meipass=str(tmp_path / "bundle"),
            win_data=wd,
            win_logs=wl,
            env={"FIN_LOG_DIR": str(custom)},
        ) as s:
            assert s["LOG_DIR"] == custom
