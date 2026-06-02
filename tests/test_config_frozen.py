"""Tests for frozen-mode path detection in fin/config.py and fin/logger.py."""

import importlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import platformdirs


@contextmanager
def _frozen_sys(meipass_dir: Path):
    """Context manager that sets sys.frozen + sys._MEIPASS, then restores original state."""
    old_frozen = getattr(sys, "frozen", _SENTINEL := object())
    old_meipass = getattr(sys, "_MEIPASS", _SENTINEL)

    sys.frozen = True
    sys._MEIPASS = str(meipass_dir)
    try:
        yield
    finally:
        if old_frozen is _SENTINEL:
            try:
                del sys.frozen
            except AttributeError:
                pass
        else:
            sys.frozen = old_frozen

        if old_meipass is _SENTINEL:
            try:
                del sys._MEIPASS
            except AttributeError:
                pass
        else:
            sys._MEIPASS = old_meipass


class TestDevMode:
    """Non-frozen (normal dev) mode keeps existing behaviour."""

    def test_data_dir_is_under_project_root(self):
        import fin.config as cfg

        project_root = Path(__file__).parent.parent
        assert cfg.DATA_DIR in (project_root / "data", project_root / "data-dev")

    def test_symbols_path_is_under_project_root(self):
        import fin.config as cfg

        project_root = Path(__file__).parent.parent
        assert cfg.SYMBOLS_PATH == project_root / "config" / "symbols.json"

    def test_frontend_dir_is_under_project_root(self):
        import fin.config as cfg

        project_root = Path(__file__).parent.parent
        assert cfg.FRONTEND_DIR == project_root / "frontend"

    def test_data_dir_exists(self):
        import fin.config as cfg

        assert cfg.DATA_DIR.exists()

    def test_log_dir_exists(self):
        import fin.config as cfg

        assert cfg.LOG_DIR.exists()


class TestFrozenMode:
    """Frozen mode redirects mutable paths to OS user dirs."""

    def _reload_frozen(self, meipass_dir: Path):
        import fin.config as cfg

        with _frozen_sys(meipass_dir):
            importlib.reload(cfg)
            data_dir = cfg.DATA_DIR
            log_dir = cfg.LOG_DIR
            frontend_dir = cfg.FRONTEND_DIR
            symbols_path = cfg.SYMBOLS_PATH
            fin_dev = cfg.FIN_DEV

        # Restore normal module state for other tests
        importlib.reload(cfg)
        return data_dir, log_dir, frontend_dir, symbols_path, fin_dev

    def test_data_dir_uses_os_user_data_dir(self, tmp_path):
        data_dir, _, _, _, _ = self._reload_frozen(tmp_path / "bundle")
        assert data_dir == Path(platformdirs.user_data_dir("Fin"))

    def test_log_dir_uses_os_user_log_dir(self, tmp_path):
        _, log_dir, _, _, _ = self._reload_frozen(tmp_path / "bundle")
        assert log_dir == Path(platformdirs.user_log_dir("Fin"))

    def test_frontend_dir_points_into_meipass(self, tmp_path):
        bundle_dir = tmp_path / "bundle"
        _, _, frontend_dir, _, _ = self._reload_frozen(bundle_dir)
        assert frontend_dir == bundle_dir / "frontend"

    def test_symbols_path_points_into_meipass(self, tmp_path):
        bundle_dir = tmp_path / "bundle"
        _, _, _, symbols_path, _ = self._reload_frozen(bundle_dir)
        assert symbols_path == bundle_dir / "config" / "symbols.json"

    def test_data_dir_not_inside_bundle(self, tmp_path):
        bundle_dir = tmp_path / "bundle"
        data_dir, _, _, _, _ = self._reload_frozen(bundle_dir)
        assert not str(data_dir).startswith(str(bundle_dir))

    def test_data_dir_created_automatically(self, tmp_path):
        data_dir, _, _, _, _ = self._reload_frozen(tmp_path / "bundle")
        assert data_dir.exists()

    def test_log_dir_created_automatically(self, tmp_path):
        _, log_dir, _, _, _ = self._reload_frozen(tmp_path / "bundle")
        assert log_dir.exists()

    def test_fin_dev_is_false_in_frozen_mode(self, tmp_path):
        _, _, _, _, fin_dev = self._reload_frozen(tmp_path / "bundle")
        assert fin_dev is False


class TestLoggerFrozenMode:
    """logger.py DEFAULT_LOG_DIR follows frozen-mode detection."""

    def test_default_log_dir_uses_platformdirs_when_frozen(self):
        import fin.logger as lg

        with _frozen_sys(Path("/fake/meipass")):
            importlib.reload(lg)
            default_log_dir = lg.DEFAULT_LOG_DIR

        importlib.reload(lg)  # restore
        assert default_log_dir == platformdirs.user_log_dir("Fin")

    def test_default_log_dir_uses_project_root_in_dev_mode(self):
        import fin.logger as lg

        importlib.reload(lg)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(lg.__file__)))
        assert lg.DEFAULT_LOG_DIR == os.path.join(project_root, "logs")
