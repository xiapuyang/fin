import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from fin.config import MARKET_STATE_PATH, SYMBOLS_PATH
from fin.database import get_db
from fin.models.alert import AlertFireModel, AlertModel
from fin.repositories.alert_fire_sqlite import AlertFireSQLiteRepository
from fin.repositories.alert_sqlite import AlertSQLiteRepository
from fin.repositories.watchlist_sqlite import WatchlistSQLiteRepository
from fin.repositories.stock_sqlite import StockSQLiteRepository
from fin.schemas.alert import (
    AlertCreate,
    AlertResponse,
    AlertUpdate,
    HistoryResponse,
    TriggeredInfo,
)
from fin.services.providers import build_default_providers
from fin.services.quote import QuoteService, normalize_symbol as _normalize_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _guess_market(symbol: str) -> str:
    """Infer market from symbol format or well-known HK index prefixes."""
    if symbol.endswith(".HK") or symbol.startswith(("^HSI", "^HSCE", "^HSTECH")):
        return "HK"
    if symbol.endswith(".SS") or symbol.endswith(".SZ"):
        return "CN"
    return "US"


def _to_response(alert: AlertModel) -> AlertResponse:
    triggered = None
    if not alert.enabled and alert.fires:
        latest: AlertFireModel = max(alert.fires, key=lambda f: f.fired_at)
        triggered = TriggeredInfo(
            at=latest.fired_at.strftime("%Y-%m-%d %H:%M"),
            price=latest.price,
        )
    return AlertResponse(
        id=alert.id,
        code=alert.symbol,
        name=alert.name,
        cond=alert.condition,
        threshold=alert.value,
        enabled=alert.enabled,
        triggered=triggered,
        created=alert.created_at.strftime("%Y-%m-%d"),
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/market-states")
def get_market_states():
    """Return current market open/close states from market_state.json.

    Written by the market_state_updater background thread (every 5 minutes).
    Falls back to an empty dict if the file is missing or unreadable.
    """
    try:
        return json.loads(MARKET_STATE_PATH.read_text())
    except Exception:
        return {}


@router.get("/quote/{symbol}")
def get_quote(symbol: str, db: Session = Depends(get_db)):
    result = QuoteService(db, build_default_providers()).get_quote(symbol)
    if result is None:
        raise HTTPException(status_code=503, detail="Price data unavailable")
    return result


@router.get("/prices")
def get_prices(symbols: str = "", db: Session = Depends(get_db)):
    """Return cached price data for a comma-separated list of symbols."""
    codes = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    svc = QuoteService(db, build_default_providers())
    result = {}
    for code in codes:
        q = svc.get_quote(code)
        if q:
            result[code] = {
                "price": q["price"],
                "prev_close": q["prev_close"],
                "regular_close": q.get("regular_close"),
                "after_hours_change_pct": q.get("after_hours_change_pct"),
                "market_state": q.get("market_state"),
                "asset_type": q.get("asset_type"),
            }
    return result


@router.get("/symbols")
def get_symbols():
    if not SYMBOLS_PATH.exists():
        raise HTTPException(status_code=404, detail="symbols.json not found")
    return json.loads(SYMBOLS_PATH.read_text())


@router.get("/alerts", response_model=list[AlertResponse])
def list_alerts(enabled: bool | None = None, db: Session = Depends(get_db)):
    repo = AlertSQLiteRepository(db)
    alerts = repo.get_enabled() if enabled is True else repo.get_all()
    return [_to_response(a) for a in alerts]


def _check_duplicate(
    repo: AlertSQLiteRepository,
    symbol: str,
    condition: str,
    value: float,
    exclude_id: int | None = None,
) -> None:
    existing = [
        a
        for a in repo.get_all()
        if a.symbol == symbol
        and a.condition == condition
        and a.value == value
        and (exclude_id is None or a.id != exclude_id)
    ]
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate alert: {symbol} {condition} {value} already exists",
        )


@router.post("/alerts", response_model=AlertResponse, status_code=201)
def create_alert(data: AlertCreate, db: Session = Depends(get_db)):
    normalized = AlertCreate(
        symbol=_normalize_symbol(data.symbol),
        name=data.name,
        condition=data.condition,
        value=data.value,
    )
    repo = AlertSQLiteRepository(db)
    _check_duplicate(repo, normalized.symbol, normalized.condition, normalized.value)
    alert = repo.create(normalized)
    logger.info(
        "Created alert %s for %s %s %s",
        alert.id,
        alert.symbol,
        alert.condition,
        alert.value,
    )

    # Auto-add symbol to watchlist — best-effort side effect, never fails the alert
    try:
        QuoteService(db, build_default_providers()).get_quote(
            normalized.symbol
        )  # populates stock cache if missing
        stock = StockSQLiteRepository(db).get_by_symbol(normalized.symbol)
        WatchlistSQLiteRepository(db).add(
            symbol=normalized.symbol,
            name=stock.name if stock else None,
            market=_guess_market(normalized.symbol),
            currency=stock.currency if stock else "USD",
        )
    except Exception:
        logger.warning(
            "Watchlist auto-add failed for %s (non-fatal)", normalized.symbol
        )

    return _to_response(alert)


@router.put("/alerts/{alert_id}", response_model=AlertResponse)
def update_alert(alert_id: int, data: AlertUpdate, db: Session = Depends(get_db)):
    repo = AlertSQLiteRepository(db)
    if data.condition is not None or data.value is not None:
        current = repo.get_by_id(alert_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        symbol = current.symbol
        condition = data.condition if data.condition is not None else current.condition
        value = data.value if data.value is not None else current.value
        _check_duplicate(repo, symbol, condition, value, exclude_id=alert_id)
    try:
        alert = repo.update(alert_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_response(alert)


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    repo = AlertSQLiteRepository(db)
    repo.delete(alert_id)
    return Response(status_code=204)


@router.post("/alerts/{alert_id}/reset", response_model=AlertResponse)
def reset_alert(alert_id: int, db: Session = Depends(get_db)):
    repo = AlertSQLiteRepository(db)
    try:
        alert = repo.reset(alert_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.info("Reset alert %s (%s)", alert_id, alert.symbol)
    return _to_response(alert)


@router.get("/history", response_model=list[HistoryResponse])
def get_history(limit: int = 50, db: Session = Depends(get_db)):
    repo = AlertFireSQLiteRepository(db)
    fires = repo.get_recent(limit)
    return [
        HistoryResponse(
            id=f.id,
            time=f.fired_at.strftime("%Y-%m-%d %H:%M"),
            code=f.alert.symbol if f.alert else "",
            name=f.alert.name if f.alert else "",
            cond=f.alert.condition if f.alert else "",
            threshold=f.alert.value if f.alert else 0.0,
            actual=f.price,
            change_pct=f.change_pct,
        )
        for f in fires
    ]
