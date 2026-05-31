import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

# Load .env from the project root if present. Silent no-op when missing,
# so production deployments that rely on real environment variables still work.
load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DB_PATH = DATA_DIR / "fin.db"
SYMBOLS_PATH = DATA_DIR / "symbols.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
LEDGER_CATEGORIES_PATH = DATA_DIR / "ledger_categories.json"
LAST_CHECK_PATH = DATA_DIR / "last_check.json"
MARKET_STATE_PATH = DATA_DIR / "market_state.json"

API_HOST = "0.0.0.0"
API_PORT = 8899

SUPPORTED_CURRENCIES: list[str] = ["CNY", "USD", "HKD", "CAD"]

TS_FMT = "%Y-%m-%d %H:%M:%S"

# Env-driven config. See .env.example for descriptions.
AGENTMAIL_API_KEY = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX = os.environ.get("FIN_AGENTMAIL_INBOX", "")

# Ensure directories exist at import time
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
