import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from fin.config import APP_CONFIG_PATH
from fin.database import get_db
from fin.models.account import AccountModel
from fin.models.benchmark_result import BenchmarkResultModel
from fin.models.user import MOCK_USER_ID
from fin.services.price_history_service import fetch_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/benchmark")

_DEFAULT_SINCE_YEARS = 10

# Cache default schemes at module load time (static config file)
_DEFAULTS_CACHE: Optional[list[dict]] = None


def _get_defaults() -> list[dict]:
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is None:
        try:
            cfg = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
            _DEFAULTS_CACHE = cfg.get("benchmark_defaults", [])
        except Exception as exc:
            logger.warning("Failed to load benchmark_defaults: %s", exc)
            _DEFAULTS_CACHE = []
    return _DEFAULTS_CACHE


# ── Schemas ───────────────────────────────────────────────────────────────────


class AllocationItem(BaseModel):
    symbol: str
    pct: float


class CustomScheme(BaseModel):
    id: Optional[str] = None
    name: str
    allocations: list[AllocationItem]
    cash_pct: float = 0.0

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()


class SchemesPayload(BaseModel):
    enabled_defaults: list[str]
    custom_schemes: list[CustomScheme] = []


class BenchmarkResultResponse(BaseModel):
    portfolio_xirr: Optional[float]
    schemes: list[dict]
    computed_date: Optional[str]
    excluded_deposits: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_account_or_404(db: Session, account_id: int) -> AccountModel:
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == MOCK_USER_ID)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.benchmark_enabled != "1":
        raise HTTPException(
            status_code=404, detail="Benchmark not enabled for this account"
        )
    return account


def _latest_result(db: Session, account_id: int) -> Optional[BenchmarkResultModel]:
    return (
        db.query(BenchmarkResultModel)
        .filter(BenchmarkResultModel.account_id == account_id)
        .order_by(BenchmarkResultModel.computed_date.desc())
        .first()
    )


def _result_to_response(row: BenchmarkResultModel) -> dict:
    schemes = []
    if row.results_json:
        try:
            schemes = json.loads(row.results_json)
        except json.JSONDecodeError:
            pass
    return {
        "portfolio_xirr": row.portfolio_xirr,
        "schemes": schemes,
        "computed_date": row.computed_date,
        "excluded_deposits": row.excluded_deposits or 0,
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/defaults")
def get_defaults():
    """Return the list of default benchmark schemes from config/app.json."""
    return _get_defaults()


@router.get("/results/{account_id}", response_model=BenchmarkResultResponse)
def get_results(account_id: int, db: Session = Depends(get_db)):
    """Return the latest computed benchmark results for an account."""
    _get_account_or_404(db, account_id)
    row = _latest_result(db, account_id)
    if row is None:
        return {
            "portfolio_xirr": None,
            "schemes": [],
            "computed_date": None,
            "excluded_deposits": 0,
        }
    return _result_to_response(row)


@router.post("/compute/{account_id}", response_model=BenchmarkResultResponse)
def compute_benchmark(account_id: int, db: Session = Depends(get_db)):
    """Trigger benchmark computation. Returns cached result if already computed today."""
    _get_account_or_404(db, account_id)
    today = str(datetime.now(timezone.utc).date())

    # Return cached result if today's row already exists
    existing = (
        db.query(BenchmarkResultModel)
        .filter(
            BenchmarkResultModel.account_id == account_id,
            BenchmarkResultModel.computed_date == today,
        )
        .first()
    )
    if existing:
        return _result_to_response(existing)

    from fin.services.benchmark_service import compute as benchmark_compute

    try:
        result = benchmark_compute(db, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


@router.put("/schemes/{account_id}")
def update_schemes(
    account_id: int, payload: SchemesPayload, db: Session = Depends(get_db)
):
    """Update enabled default schemes and custom schemes for an account."""
    account = _get_account_or_404(db, account_id)

    # Validate: enabled_defaults must all be known IDs
    default_ids = {d["id"] for d in _get_defaults()}
    unknown = [i for i in payload.enabled_defaults if i not in default_ids]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown default scheme IDs: {unknown}",
        )

    # Validate custom schemes: allocations + cash_pct must sum to 100%
    for cs in payload.custom_schemes:
        alloc_sum = sum(a.pct for a in cs.allocations) + cs.cash_pct
        if abs(alloc_sum - 100.0) > 0.01:
            raise HTTPException(
                status_code=422,
                detail=f"Custom scheme '{cs.name}': allocations + cash_pct must sum to 100% (got {alloc_sum:.1f}%)",
            )
        if not cs.allocations:
            raise HTTPException(
                status_code=422,
                detail=f"Custom scheme '{cs.name}': must have at least one allocation",
            )

    # Assign IDs to new custom schemes
    custom_list = []
    for cs in payload.custom_schemes:
        scheme_id = cs.id or str(uuid.uuid4())[:8]
        custom_list.append(
            {
                "id": scheme_id,
                "name": cs.name,
                "allocations": [
                    {"symbol": a.symbol, "pct": a.pct} for a in cs.allocations
                ],
                "cash_pct": cs.cash_pct,
            }
        )

    schemes_json = json.dumps(
        {
            "enabled_defaults": payload.enabled_defaults,
            "custom_schemes": custom_list,
        }
    )
    account.benchmark_schemes = schemes_json
    db.commit()
    db.refresh(account)

    return json.loads(account.benchmark_schemes)


@router.get("/prices")
def get_prices(
    symbol: str = Query(..., description="Ticker symbol"),
    since: str = Query(
        None, description="Start date YYYY-MM-DD; defaults to 10 years ago"
    ),
    db: Session = Depends(get_db),
):
    """Return historical close prices for a symbol, fetching from yfinance if stale."""
    if since is None:
        since = str(
            (
                datetime.now(timezone.utc) - timedelta(days=_DEFAULT_SINCE_YEARS * 365)
            ).date()
        )
    return fetch_symbol(db, symbol, since)
