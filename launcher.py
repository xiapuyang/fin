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
import threading
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

logger = logging.getLogger(__name__)

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
    """Called by pystray in a background thread once the icon is running.

    By the time this runs, the port-conflict check in main() has already
    passed, so the port is guaranteed free and we can start the server.
    """
    from fin.api import app  # import here so config.py already ran with frozen flag

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            workers=1,
            log_level="warning",
        )
    )

    # Store on icon so Quit handler can reach it.
    icon._fin_server = server

    t = threading.Thread(
        target=lambda: asyncio.run(server.serve()),
        daemon=True,
        name="uvicorn",
    )
    t.start()

    if not _wait_for_server():
        logger.warning("Server did not respond in time — opening browser anyway")
    _open_browser()


def _quit(icon, item) -> None:
    """Gracefully shut down uvicorn then stop the tray icon."""
    server = getattr(icon, "_fin_server", None)
    if server is not None:
        server.should_exit = True
    icon.stop()


def _open_action(icon, item) -> None:
    _open_browser()


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

    import pystray
    from PIL import Image

    icon_path = _resource_path("assets/tray_icon.png")
    try:
        image = Image.open(icon_path)
    except Exception:
        # Fallback: 32×32 solid square if icon file is missing.
        image = Image.new("RGB", (32, 32), color=(30, 120, 200))

    menu = pystray.Menu(
        pystray.MenuItem("Open Fin", _open_action, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit),
    )
    icon = pystray.Icon("fin", image, "Fin", menu)
    icon.run(setup=_on_tray_ready)


if __name__ == "__main__":
    main()
