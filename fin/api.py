import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fin.config import FRONTEND_DIR
from fin.database import init_db
from fin.logger import setup_logging
from fin.middleware import LoggingMiddleware
from fin.routers.alerts import router as alerts_router
from fin.routers.balance import router as balance_router
from fin.routers.categories import router as categories_router
from fin.routers.holdings import router as holdings_router
from fin.routers.ledger import router as ledger_router
from fin.routers.settings import router as settings_router
from fin.routers.watchlist import router as watchlist_router
from fin.services.market_state_updater import start_market_state_updater
from fin.services.price_updater import start_price_updater

setup_logging("fin-api")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")
    start_market_state_updater()
    start_price_updater()
    yield
    logger.info("Shutting down")


app = FastAPI(title="fin API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(categories_router)
app.include_router(holdings_router)
app.include_router(ledger_router)
app.include_router(settings_router)
app.include_router(watchlist_router)

_STATIC_VER = str(int(time.time()))


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (FRONTEND_DIR / "index.html").read_text()
    return html.replace("__VER__", _STATIC_VER)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
