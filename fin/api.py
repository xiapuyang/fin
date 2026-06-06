import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fin.config import (
    API_HOST,
    API_PORT,
    APP_CONFIG_PATH,
    CONFIG_DIR,
    DATA_DIR,
    FRONTEND_DIR,
    HOME_FIN,
    PROJECT_ROOT,
)
from fin.data_migration import migrate_data_dir
from fin.database import init_db
from fin.logger import setup_logging
from fin.middleware import LoggingMiddleware
from fin.routers.alerts import router as alerts_router
from fin.routers.balance import router as balance_router
from fin.routers.benchmark import router as benchmark_router
from fin.routers.categories import router as categories_router
from fin.routers.holdings import router as holdings_router
from fin.routers.ledger import router as ledger_router
from fin.routers.meta import router as meta_router
from fin.routers.settings import router as settings_router
from fin.routers.watchlist import router as watchlist_router
from fin.services.alert_scheduler import start_alert_scheduler, stop_alert_scheduler
from fin.services.benchmark_scheduler import (
    start_benchmark_backfill,
    start_benchmark_scheduler,
    stop_benchmark_backfill,
    stop_benchmark_scheduler,
)
from fin.services.benchmark_service import warn_orphaned_bench_ids
from fin.services.market_state_updater import start_market_state_updater
from fin.services.price_updater import start_price_updater

setup_logging("fin-api")
logger = logging.getLogger(__name__)

_ALERT_SCHEDULER_STOP = None
_BENCHMARK_SCHEDULER_STOP = None
_BENCHMARK_BACKFILL_STOP = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ALERT_SCHEDULER_STOP, _BENCHMARK_SCHEDULER_STOP, _BENCHMARK_BACKFILL_STOP
    migrate_data_dir(DATA_DIR, HOME_FIN, PROJECT_ROOT)
    init_db()
    logger.info("Database initialized")
    warn_orphaned_bench_ids()
    start_market_state_updater()
    start_price_updater()
    _BENCHMARK_BACKFILL_STOP = start_benchmark_backfill()
    logger.info("Benchmark backfill thread started")
    is_dev = bool(os.environ.get("FIN_DEV"))
    if getattr(sys, "frozen", False) or not is_dev:
        _ALERT_SCHEDULER_STOP = start_alert_scheduler()
        logger.info("Alert scheduler started")
        _BENCHMARK_SCHEDULER_STOP = start_benchmark_scheduler()
        logger.info("Benchmark scheduler started")
    yield
    if _ALERT_SCHEDULER_STOP is not None:
        stop_alert_scheduler(_ALERT_SCHEDULER_STOP)
    if _BENCHMARK_SCHEDULER_STOP is not None:
        stop_benchmark_scheduler(_BENCHMARK_SCHEDULER_STOP)
    if _BENCHMARK_BACKFILL_STOP is not None:
        stop_benchmark_backfill(_BENCHMARK_BACKFILL_STOP)
    logger.info("Shutting down")


app = FastAPI(title="fin API", lifespan=lifespan)

# Same-origin only. Wildcard origins would let a malicious page reach this
# server via DNS rebinding and read stored credentials cross-origin.
_ALLOWED_ORIGINS = [
    f"http://127.0.0.1:{API_PORT}",
    f"http://localhost:{API_PORT}",
]
if API_HOST not in ("127.0.0.1", "0.0.0.0", "localhost"):
    _ALLOWED_ORIGINS.append(f"http://{API_HOST}:{API_PORT}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Prevent browser caching of API responses and local JS/JSX files."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") or path.endswith((".jsx", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(alerts_router)
app.include_router(balance_router)
app.include_router(benchmark_router)
app.include_router(categories_router)
app.include_router(holdings_router)
app.include_router(ledger_router)
app.include_router(meta_router)
app.include_router(settings_router)
app.include_router(watchlist_router)

_STATIC_VER = str(int(time.time()))


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    return html.replace("__VER__", _STATIC_VER)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/config/app.json")
async def serve_app_config():
    """Serve config/app.json so the frontend reads the same source as the backend."""
    return JSONResponse(content=json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8")))


@app.get("/i18n", response_class=HTMLResponse)
async def i18n_manager():
    return (FRONTEND_DIR / "i18n.html").read_text(encoding="utf-8")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, RuntimeError) and "Content-Length" in str(exc):
        # Transport-layer error: headers were already committed and the body
        # stream was cut short. There is nothing useful to send back — the
        # connection is broken. Re-raise so uvicorn closes it cleanly.
        raise exc
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


_I18N_DIR = CONFIG_DIR / "i18n"
if _I18N_DIR.exists():
    # Scope to i18n/ only — mounting all of config/ would also serve .env.example
    # and any future files dropped in there.
    app.mount("/config/i18n", StaticFiles(directory=str(_I18N_DIR)), name="i18n")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
