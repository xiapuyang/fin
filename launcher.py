#!/usr/bin/env python3
"""Desktop entry point for the packaged Fin app.

Starts the FastAPI server in a background thread, shows a system tray icon,
and opens the browser once the server is ready. Must be the PyInstaller
entrypoint so that multiprocessing.freeze_support() runs before anything else.
"""

import asyncio
import logging
import multiprocessing
import socket
import sys
import tempfile
import threading
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from fin._version import __version__ as APP_VERSION

# Write to a temp log file so errors are visible even with console=False
_LOG_FILE = Path(tempfile.gettempdir()) / "fin_launcher.log"
logging.basicConfig(
    filename=str(_LOG_FILE),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

GITHUB_REPO = "xiapuyang/fin"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

HOST = "127.0.0.1"
PORT = 8888
BASE_URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{BASE_URL}/api/health"
HEALTH_RETRIES = 30
HEALTH_INTERVAL = 0.5


def _resource_path(relative: str) -> Path:
    """Resolve a path to a bundled asset.

    In frozen mode, assets live under sys._MEIPASS. In dev mode they live
    next to this file.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent
    return base / relative


def _port_is_open() -> bool:
    """Return True if something is already listening on HOST:PORT."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _health_ok() -> bool:
    """Return True if the fin health endpoint returns 200."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _wait_for_server() -> bool:
    """Poll the health endpoint; return True once ready, False on timeout."""
    import time

    for _ in range(HEALTH_RETRIES):
        if _health_ok():
            return True
        time.sleep(HEALTH_INTERVAL)
    return False


def _show_error(title: str, message: str) -> None:
    """Show a native OS error dialog without tkinter."""
    if sys.platform == "darwin":
        import subprocess

        subprocess.run(
            [
                "osascript",
                "-e",
                f'display alert "{title}" message "{message}" as critical',
            ],
            check=False,
        )
    elif sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    else:
        print(f"[{title}] {message}", file=sys.stderr)


def _open_browser() -> None:
    webbrowser.open(BASE_URL)


def _on_tray_ready(icon) -> None:
    icon.visible = True


def _quit(icon, item) -> None:
    """Gracefully shut down uvicorn then stop the tray icon."""
    server = getattr(icon, "_fin_server", None)
    if server is not None:
        server.should_exit = True
    icon.stop()


def _open_action(icon, item) -> None:
    _open_browser()


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x.split("-")[0]) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def _sanitize_for_applescript(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _show_info(title: str, message: str) -> None:
    if sys.platform == "darwin":
        import subprocess

        safe_title = _sanitize_for_applescript(title)
        safe_message = _sanitize_for_applescript(message)
        icon_path = _resource_path("assets/fin.icns")
        icon_clause = (
            f' with icon file POSIX file "{icon_path}"' if icon_path.exists() else ""
        )
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display dialog "{safe_message}" with title "{safe_title}" buttons {{"OK"}} default button "OK"{icon_clause}',
            ],
            check=False,
        )
    elif sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    else:
        print(f"[{title}] {message}")


def _prompt_update(latest_tag: str, release_notes: str = "") -> None:
    safe_tag = _sanitize_for_applescript(latest_tag)
    safe_notes = _sanitize_for_applescript(release_notes[:300])
    notes_line = f"\n\n{safe_notes}" if release_notes else ""
    message = f"发现新版本 {safe_tag}（当前 v{APP_VERSION}）。{notes_line}\n\n是否前往下载页面？"
    should_open = False
    if sys.platform == "darwin":
        import subprocess

        icon_path = _resource_path("assets/fin.icns")
        icon_clause = (
            f' with icon file POSIX file "{icon_path}"' if icon_path.exists() else ""
        )
        result = subprocess.run(
            [
                "osascript",
                "-e",
                f'display dialog "{message}" buttons {{"稍后", "前往下载"}} default button "前往下载"{icon_clause}',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        should_open = "前往下载" in result.stdout
    elif sys.platform == "win32":
        import ctypes

        ret = ctypes.windll.user32.MessageBoxW(0, message, "Fin 更新", 0x24)
        should_open = ret == 6  # IDYES
    if should_open:
        webbrowser.open(RELEASES_URL)


def _check_for_updates(icon, item) -> None:
    import json

    def _do_check() -> None:
        try:
            req = urllib.request.Request(
                RELEASES_API_URL, headers={"User-Agent": "fin-app"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            latest_tag = data.get("tag_name", "")
            if _version_tuple(latest_tag) > _version_tuple(APP_VERSION):
                _prompt_update(latest_tag, data.get("body", ""))
            else:
                _show_info("Fin", f"已是最新版本（v{APP_VERSION}）。")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # No releases published yet — treat as up to date
                _show_info("Fin", f"已是最新版本（v{APP_VERSION}）。")
            else:
                logger.warning("Update check failed: %s", exc)
                _show_error("Fin", "检查更新失败，请稍后重试。")
        except Exception as exc:
            logger.warning("Update check failed: %s", exc)
            _show_error("Fin", "检查更新失败，请稍后重试。")

    threading.Thread(target=_do_check, daemon=True, name="update-check").start()


def main() -> None:
    """Entry point. Must be called before any other application code."""
    multiprocessing.freeze_support()

    # Resolve port conflicts before creating the tray icon so a second launch
    # never leaves a ghost icon with no server behind it.
    if _port_is_open():
        if _health_ok():
            logger.info("Fin already running on port %d — opening browser", PORT)
            _open_browser()
            return
        else:
            _show_error(
                "Fin",
                f"Port {PORT} is occupied by another process. Close it and try again.",
            )
            sys.exit(1)

    try:
        logger.info("importing fin.api")
        from fin.api import app

        logger.info("fin.api imported ok")
    except Exception:
        logger.exception("failed to import fin.api")
        raise

    server = uvicorn.Server(
        uvicorn.Config(app, host=HOST, port=PORT, workers=1, log_level="warning")
    )

    def _run_server() -> None:
        try:
            logger.info("uvicorn starting on %s:%s", HOST, PORT)
            asyncio.run(server.serve())
        except Exception:
            logger.exception("uvicorn crashed")

    threading.Thread(target=_run_server, daemon=True, name="uvicorn").start()

    def _open_when_ready() -> None:
        if not _wait_for_server():
            logger.warning("Server did not respond in time — opening browser anyway")
        _open_browser()

    threading.Thread(target=_open_when_ready, daemon=True, name="browser-open").start()

    import pystray
    from PIL import Image

    icon_path = _resource_path("assets/tray_icon.png")
    try:
        image = Image.open(icon_path)
    except Exception:
        image = Image.new("RGB", (32, 32), color=(30, 120, 200))

    menu = pystray.Menu(
        pystray.MenuItem("Open Fin", _open_action, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Check for Updates…", _check_for_updates),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )
    icon = pystray.Icon("fin", image, "Fin", menu)
    icon._fin_server = server
    icon.run(setup=_on_tray_ready)


if __name__ == "__main__":
    main()
