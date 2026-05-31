import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

# Load .env from the project root if present. Silent no-op when missing,
# so production deployments that rely on real environment variables still work.
load_dotenv(PROJECT_ROOT / ".env")

# Dev/prod split. FIN_DEV=1 (set by `serve.py --dev`) routes all personal data
# to data-dev/ on a different port. Skill writes from a dev machine to prod are
# blocked by ~/.fin-dev marker — see skills/fin-import/scripts/post_bulk.py.
FIN_DEV = os.environ.get("FIN_DEV") == "1"
DATA_DIR = PROJECT_ROOT / ("data-dev" if FIN_DEV else "data")
LOG_DIR = PROJECT_ROOT / "logs"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Personal/mutable state — lives under DATA_DIR, toggled by FIN_DEV.
# FIN_DB_PATH explicit override beats both (tests/smoke use it).
DB_PATH = Path(os.environ.get("FIN_DB_PATH") or (DATA_DIR / "fin.db"))
SETTINGS_PATH = DATA_DIR / "settings.json"
LEDGER_CATEGORIES_PATH = DATA_DIR / "ledger_categories.json"
LAST_CHECK_PATH = DATA_DIR / "last_check.json"
MARKET_STATE_PATH = DATA_DIR / "market_state.json"

# Static shared config — committed, ships with code, identical across dev/prod.
SYMBOLS_PATH = PROJECT_ROOT / "config" / "symbols.json"

API_HOST = "0.0.0.0"
API_PORT = int(os.environ.get("FIN_PORT") or ("18899" if FIN_DEV else "8899"))

SUPPORTED_CURRENCIES: list[str] = ["CNY", "USD", "HKD", "CAD"]

TS_FMT = "%Y-%m-%d %H:%M:%S"

# Env-driven config. See .env.example for descriptions.
AGENTMAIL_API_KEY = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX = os.environ.get("FIN_AGENTMAIL_INBOX", "")

# Ensure directories exist at import time
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
