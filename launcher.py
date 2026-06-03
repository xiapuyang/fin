#!/usr/bin/env python3
"""Desktop entry point for the packaged Fin app.

Starts the FastAPI server in a background thread, shows a system tray icon,
and opens the browser once the server is ready. Must be the PyInstaller
entrypoint so that multiprocessing.freeze_support() runs before anything else.
"""

import logging
import multiprocessing
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from fin._version import __version__ as APP_VERSION
from fin.i18n import t

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


_WIN32_MUTEX_NAME = "Global\\FinAppSingleInstance"
_WIN32_ERROR_ALREADY_EXISTS = 183
_WIN32_GWL_EXSTYLE = -20
_WIN32_WS_EX_TOOLWINDOW = 0x00000080
_WIN32_WS_EX_APPWINDOW = 0x00040000
_win32_mutex_handle = None  # keep alive for process lifetime


def _acquire_single_instance_mutex() -> bool:
    """On Windows, grab a named mutex to prevent multiple instances.

    Returns True if this is the first instance, False if another is already running.
    The mutex must stay referenced for the lifetime of the process — released on exit
    automatically by the OS.
    """
    global _win32_mutex_handle
    if sys.platform != "win32":
        return True
    import ctypes

    handle = ctypes.windll.kernel32.CreateMutexW(None, False, _WIN32_MUTEX_NAME)
    if not handle:
        return True  # CreateMutex failed — allow launch
    if ctypes.windll.kernel32.GetLastError() == _WIN32_ERROR_ALREADY_EXISTS:
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    _win32_mutex_handle = handle  # prevent GC
    return True


def _hide_from_taskbar(icon) -> None:
    """Remove the pystray message window from the Windows taskbar.

    pystray creates a WS_POPUP top-level window for its Win32 message loop.
    Without WS_EX_TOOLWINDOW, Windows may add a taskbar button alongside the
    tray icon, producing two visible indicators for the same app.
    """
    if sys.platform != "win32":
        return
    import ctypes

    hwnd = getattr(icon, "_hwnd", None)
    if not hwnd:
        return
    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, _WIN32_GWL_EXSTYLE)
    ex_style = (ex_style | _WIN32_WS_EX_TOOLWINDOW) & ~_WIN32_WS_EX_APPWINDOW
    ctypes.windll.user32.SetWindowLongW(hwnd, _WIN32_GWL_EXSTYLE, ex_style)


def _on_tray_ready(icon) -> None:
    _hide_from_taskbar(icon)
    icon.visible = True


def _quit(icon, item) -> None:
    """Gracefully shut down uvicorn then stop the tray icon."""
    server = getattr(icon, "_fin_server", None)
    if server is not None:
        server.should_exit = True
    icon.stop()


def _open_action(icon, item) -> None:
    _open_browser()


def _open_about(icon, item) -> None:
    """Show a native About dialog. No browser jump — same info as the in-app page.

    Runs in a worker thread so the blocking Win32 MessageBoxW does not share
    pystray's tray-thread message pump (which prevents the OK button from
    delivering WM_COMMAND and leaves the dialog unclosable on Windows).
    """
    body = "\n".join(
        [
            t("about.tagline"),
            "",
            f"{t('about.version')}: v{APP_VERSION}",
            f"{t('about.license')}: MIT",
            f"{t('about.github')}: https://github.com/{GITHUB_REPO}",
            "",
            t("about.copyright"),
        ]
    )
    threading.Thread(
        target=_show_info,
        args=(t("about.title"), body),
        daemon=True,
        name="about-dialog",
    ).start()


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


def _prompt_update(latest_tag: str) -> None:
    safe_tag = _sanitize_for_applescript(latest_tag)
    message = t(
        "launcher.update.found",
        tag=safe_tag,
        current=APP_VERSION,
    )
    btn_later = t("launcher.update.button_later")
    btn_download = t("launcher.update.button_download")
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
                f'display dialog "{message}" buttons {{"{btn_later}", "{btn_download}"}} default button "{btn_download}"{icon_clause}',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        should_open = btn_download in result.stdout
    elif sys.platform == "win32":
        import ctypes

        ret = ctypes.windll.user32.MessageBoxW(
            0, message, t("launcher.update.title"), 0x24
        )
        should_open = ret == 6  # IDYES
    if should_open:
        webbrowser.open(RELEASES_URL)


def _check_for_updates(icon, item) -> None:
    import json
    import ssl

    import certifi

    def _do_check() -> None:
        try:
            req = urllib.request.Request(
                RELEASES_API_URL, headers={"User-Agent": "fin-app"}
            )
            ctx = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                data = json.loads(r.read())
            latest_tag = data.get("tag_name", "")
            if _version_tuple(latest_tag) > _version_tuple(APP_VERSION):
                _prompt_update(latest_tag)
            else:
                _show_info("Fin", t("launcher.update.up_to_date", current=APP_VERSION))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # No releases published yet — treat as up to date
                _show_info("Fin", t("launcher.update.up_to_date", current=APP_VERSION))
            else:
                logger.warning("Update check failed: %s", exc)
                _show_error("Fin", t("launcher.update.check_failed"))
        except Exception as exc:
            logger.warning("Update check failed: %s", exc)
            _show_error("Fin", t("launcher.update.check_failed"))

    threading.Thread(target=_do_check, daemon=True, name="update-check").start()


def main() -> None:
    """Entry point. Must be called before any other application code."""
    multiprocessing.freeze_support()

    # On Windows, grab a named mutex before anything else — faster and race-free
    # compared to port checking, which has a window between check and bind.
    if not _acquire_single_instance_mutex():
        logger.info("Another Fin instance detected via mutex — opening browser")
        if _health_ok():
            _open_browser()
        sys.exit(0)

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

    def _log(msg: str) -> None:
        """Write directly to log file — survives logging.basicConfig being reset."""
        with open(str(_LOG_FILE), "a") as _f:
            _f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    from fin.api import app

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            workers=1,
            log_level="warning",
            loop="asyncio",
            http="h11",
            log_config=None,  # skip dictConfig — factory import hangs in frozen app
        )
    )

    def _run_server() -> None:
        try:
            _log("uvicorn started")
            server.run()  # uses config's loop_factory (ProactorEventLoop on Windows)
            _log("uvicorn stopped")
        except Exception as exc:
            _log(f"uvicorn error: {exc}")

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
        pystray.MenuItem(t("launcher.tray.open"), _open_action, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("launcher.tray.about"), _open_about),
        pystray.MenuItem(t("launcher.tray.check_updates"), _check_for_updates),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("launcher.tray.quit"), _quit),
    )
    icon = pystray.Icon("fin", image, "Fin", menu)
    icon._fin_server = server
    icon.run(setup=_on_tray_ready)


if __name__ == "__main__":
    main()
