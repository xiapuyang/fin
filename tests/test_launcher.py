"""Unit tests for launcher.py — testable parts only.

Tray icon, browser open, and native dialogs are untestable in headless CI
and are covered by manual verification per the plan.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── _resource_path ────────────────────────────────────────────────────────────


def test_resource_path_dev_mode():
    """In dev mode, returns a path relative to launcher.py's directory."""
    from launcher import _resource_path

    result = _resource_path("assets/tray_icon.png")
    expected = Path(__file__).parent.parent / "assets" / "tray_icon.png"
    assert result == expected


def test_resource_path_frozen_mode(tmp_path):
    """In frozen mode, returns a path under sys._MEIPASS."""
    old_frozen = getattr(sys, "frozen", None)
    old_meipass = getattr(sys, "_MEIPASS", None)
    sys.frozen = True
    sys._MEIPASS = str(tmp_path)
    try:
        import importlib

        import launcher

        importlib.reload(launcher)
        result = launcher._resource_path("assets/tray_icon.png")
        assert result == tmp_path / "assets" / "tray_icon.png"
    finally:
        if old_frozen is None:
            try:
                del sys.frozen
            except AttributeError:
                pass
        else:
            sys.frozen = old_frozen
        if old_meipass is None:
            try:
                del sys._MEIPASS
            except AttributeError:
                pass
        else:
            sys._MEIPASS = old_meipass
        import importlib

        import launcher

        importlib.reload(launcher)


# ── health polling ────────────────────────────────────────────────────────────


def test_health_ok_returns_true_on_200():
    """_health_ok() returns True when the URL responds 200."""
    from launcher import _health_ok

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("launcher.urllib.request.urlopen", return_value=mock_response):
        assert _health_ok() is True


def test_health_ok_returns_false_on_exception():
    """_health_ok() returns False when the request raises."""
    from launcher import _health_ok

    with patch("launcher.urllib.request.urlopen", side_effect=OSError("refused")):
        assert _health_ok() is False


def test_wait_for_server_returns_true_when_health_responds(monkeypatch):
    """_wait_for_server() returns True immediately if health check passes."""
    import launcher

    monkeypatch.setattr(launcher, "_health_ok", lambda: True)
    assert launcher._wait_for_server() is True


def test_wait_for_server_returns_false_on_timeout(monkeypatch):
    """_wait_for_server() returns False after all retries exhaust."""
    import launcher

    monkeypatch.setattr(launcher, "_health_ok", lambda: False)
    monkeypatch.setattr(launcher, "HEALTH_RETRIES", 2)
    monkeypatch.setattr(launcher, "HEALTH_INTERVAL", 0)
    assert launcher._wait_for_server() is False


# ── port conflict handling (resolved in main() before tray icon is created) ───


def test_main_opens_browser_when_fin_already_running(monkeypatch):
    """When port is occupied and health is OK, open browser and return — no tray icon."""
    import launcher

    monkeypatch.setattr(launcher, "_port_is_open", lambda: True)
    monkeypatch.setattr(launcher, "_health_ok", lambda: True)
    monkeypatch.setattr(launcher, "multiprocessing", MagicMock())

    opened = []
    monkeypatch.setattr(launcher, "_open_browser", lambda: opened.append(1))

    launcher.main()

    assert opened == [1]


def test_main_shows_error_when_port_conflicts(monkeypatch):
    """When port is occupied by a non-fin process, show error and exit before tray."""
    import launcher

    monkeypatch.setattr(launcher, "_port_is_open", lambda: True)
    monkeypatch.setattr(launcher, "_health_ok", lambda: False)
    monkeypatch.setattr(launcher, "multiprocessing", MagicMock())

    errors = []
    monkeypatch.setattr(launcher, "_show_error", lambda t, m: errors.append((t, m)))

    with pytest.raises(SystemExit):
        launcher.main()

    assert errors  # an error dialog was shown before any tray icon was created
