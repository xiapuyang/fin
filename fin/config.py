import os
import sys
from pathlib import Path

import platformdirs
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
HOME_FIN = Path.home() / ".fin"

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # Running as a PyInstaller bundle. The bundle root (_MEIPASS) is read-only;
    # all mutable state goes to the OS user data dir so it survives app updates.
    BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    if sys.platform == "win32":
        DATA_DIR = Path(platformdirs.user_data_dir("Fin"))
        LOG_DIR = Path(platformdirs.user_log_dir("Fin"))
    else:
        DATA_DIR = HOME_FIN / "data"
        LOG_DIR = HOME_FIN / "logs"
    FRONTEND_DIR = BUNDLE_DIR / "frontend"
    SYMBOLS_PATH = BUNDLE_DIR / "config" / "symbols.json"
    load_dotenv(DATA_DIR / ".env")
    FIN_DEV = False
    DB_PATH = DATA_DIR / "fin.db"
    API_PORT = int(os.environ.get("FIN_PORT") or "8888")
else:
    BUNDLE_DIR = PROJECT_ROOT
    # FIN_DEV=1 (set by serve.py --dev) pins DATA_DIR, DB_PATH, and API_PORT to
    # dev values — FIN_DB_PATH / FIN_PORT overrides are ignored in dev mode.
    FIN_DEV = os.environ.get("FIN_DEV") == "1"
    LOG_DIR = HOME_FIN / "logs"
    FRONTEND_DIR = PROJECT_ROOT / "frontend"
    SYMBOLS_PATH = PROJECT_ROOT / "config" / "symbols.json"

    if FIN_DEV:
        DATA_DIR = HOME_FIN / "data-dev"
        DB_PATH = DATA_DIR / "fin.db"
        API_PORT = 18888
    else:
        DATA_DIR = HOME_FIN / "data"
        DB_PATH = Path(os.environ.get("FIN_DB_PATH") or (DATA_DIR / "fin.db"))
        API_PORT = int(os.environ.get("FIN_PORT") or "8888")
    # Load user credentials first, then project .env so local overrides win.
    load_dotenv(DATA_DIR / ".env")
    load_dotenv(PROJECT_ROOT / ".env", override=True)

# Personal/mutable state — lives under DATA_DIR.
SETTINGS_PATH = DATA_DIR / "settings.json"
LEDGER_CATEGORIES_PATH = DATA_DIR / "ledger_categories.json"
LAST_CHECK_PATH = DATA_DIR / "last_check.json"
MARKET_STATE_PATH = DATA_DIR / "market_state.json"

API_HOST = os.environ.get("FIN_HOST", "127.0.0.1")

BULK_MAX_ITEMS = 500

SUPPORTED_CURRENCIES: list[str] = ["CNY", "USD", "HKD", "CAD"]

TS_FMT = "%Y-%m-%d %H:%M:%S"

# Env-driven config. See .env.example for descriptions.
AGENTMAIL_API_KEY = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX = os.environ.get("FIN_AGENTMAIL_INBOX", "")

# Ensure directories exist at import time
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
