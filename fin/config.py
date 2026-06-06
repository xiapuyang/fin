import json
import logging
import os
import shutil
import sys
from pathlib import Path

import platformdirs
from dotenv import load_dotenv

_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
HOME_FIN = Path.home() / ".fin"
_FROZEN = getattr(sys, "frozen", False)
_win = sys.platform == "win32"

if _FROZEN:
    # Running as a PyInstaller bundle. The bundle root (_MEIPASS) is read-only;
    # all mutable state goes to the OS user data dir so it survives app updates.
    BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    FIN_DEV = False
else:
    BUNDLE_DIR = PROJECT_ROOT
    # FIN_DEV=1 (set by serve.py --dev) pins DATA_DIR, DB_PATH, and API_PORT to
    # dev values — FIN_DB_PATH / FIN_PORT overrides are ignored in dev mode.
    FIN_DEV = os.environ.get("FIN_DEV") == "1"

FRONTEND_DIR = BUNDLE_DIR / "frontend"
CONFIG_DIR = BUNDLE_DIR / "config"
SYMBOLS_PATH = CONFIG_DIR / "symbols.json"
I18N_DIR = CONFIG_DIR / "i18n"
APP_CONFIG_PATH = CONFIG_DIR / "app.json"

# Bootstrap .env — fixed location outside data/ so FIN_DATA_DIR in .env takes effect.
#   macOS/Linux : ~/.fin/.env
#   Windows     : %APPDATA%\Fin\Fin\.env  (user_config_dir, Roaming)
ENV_DIR = Path(platformdirs.user_config_dir("Fin")) if _win else HOME_FIN
ENV_PATH = ENV_DIR / ".env"
ENV_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(ENV_PATH)

if not _FROZEN:
    # Dev: project-root .env overrides bootstrap .env (local secrets take precedence).
    load_dotenv(PROJECT_ROOT / ".env", override=True)

# Default directories — used both for DATA_DIR fallback and migration source.
if _win:
    _default_data_dir = Path(platformdirs.user_data_dir("Fin"))
    _default_log_dir = Path(platformdirs.user_log_dir("Fin"))
else:
    _default_data_dir = HOME_FIN / "data"
    _default_log_dir = HOME_FIN / "logs"

# Compute DATA_DIR after loading .env so FIN_DATA_DIR override takes effect.
# FIN_DATA_DIR always wins — even over FIN_DEV — when explicitly set.
if FIN_DEV:
    _effective_default = (
        (HOME_FIN / "data-dev") if not _win else (_default_data_dir / "data-dev")
    )
    API_PORT = 18888
else:
    _effective_default = _default_data_dir
    API_PORT = int(os.environ.get("FIN_PORT") or "8888")

DATA_DIR = Path(os.environ.get("FIN_DATA_DIR") or _effective_default)

LOG_DIR = Path(os.environ.get("FIN_LOG_DIR") or _default_log_dir)
DB_PATH = (
    DATA_DIR / "fin.db"
    if (_FROZEN or FIN_DEV)
    else Path(os.environ.get("FIN_DB_PATH") or (DATA_DIR / "fin.db"))
)

# Migrate old data/.env → ENV_PATH on first run after upgrade.
# Uses the production default path (not DATA_DIR) so it works in dev mode too.
_old_env = _default_data_dir / ".env"
if _old_env.exists() and not ENV_PATH.exists():
    shutil.move(str(_old_env), ENV_PATH)
    _logger.info("Moved .env from %s to %s.", _old_env, ENV_PATH)
    load_dotenv(ENV_PATH, override=True)

# Personal/mutable state — lives under DATA_DIR.
SETTINGS_PATH = DATA_DIR / "settings.json"
LEDGER_CATEGORIES_PATH = DATA_DIR / "ledger_categories.json"
LAST_CHECK_PATH = DATA_DIR / "last_check.json"
MARKET_STATE_PATH = DATA_DIR / "market_state.json"
SYMBOL_OVERRIDES_PATH = DATA_DIR / "symbol_overrides.json"
ALERT_LOCK_PATH = DATA_DIR / "alert_check.lock"

API_HOST = os.environ.get("FIN_HOST", "127.0.0.1")

BULK_MAX_ITEMS = 500

SUPPORTED_CURRENCIES: list[str] = ["CNY", "USD", "HKD", "CAD"]

TS_FMT = "%Y-%m-%d %H:%M:%S"

# Env-driven config. See config/.env.example for descriptions.
AGENTMAIL_API_KEY = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX = os.environ.get("FIN_AGENTMAIL_INBOX", "")

# Ensure directories exist at import time
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_app_config() -> dict:
    """Read config/app.json: i18n langs + settings defaults shared across modules."""
    try:
        return json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Failed to load %s: %s", APP_CONFIG_PATH, exc)
        return {}


APP_CONFIG = load_app_config()
