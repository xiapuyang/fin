import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from fin.config import APP_CONFIG_PATH
from fin.database import get_db
from fin.models.account import AccountModel
from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
from fin.models.benchmark_result import BenchmarkResultModel
from fin.models.user import MOCK_USER_ID
from fin.services.price_history_service import fetch_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/benchmark")

_DEFAULT_SINCE_YEARS = 10
_PORTFOLIO_BENCH_ID = "__portfolio__"

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


class CustomSchemePayload(BaseModel):
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


class BenchmarkResultResponse(BaseModel):
    portfolio_xirr: Optional[float]
    portfolio_value_usd: Optional[float] = None
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


def _validate_scheme_payload(payload: CustomSchemePayload) -> None:
    if not payload.allocations:
        raise HTTPException(
            status_code=422,
            detail=f"Custom scheme '{payload.name}': must have at least one allocation",
        )
    alloc_sum = sum(a.pct for a in payload.allocations) + payload.cash_pct
    if abs(alloc_sum - 100.0) > 0.01:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Custom scheme '{payload.name}': allocations + cash_pct must sum to 100%"
                f" (got {alloc_sum:.1f}%)"
            ),
        )


def _cs_to_dict(row: BenchmarkCustomSchemeModel) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "allocations": json.loads(row.allocations_json),
        "cash_pct": row.cash_pct,
        "enabled": row.enabled if row.enabled is not None else 1,
    }


def _build_results_response(db: Session, account_id: int) -> dict:
    latest_date = (
        db.query(func.max(BenchmarkResultModel.computed_date))
        .filter(BenchmarkResultModel.account_id == account_id)
        .scalar()
    )
    if latest_date is None:
        return {
            "portfolio_xirr": None,
            "schemes": [],
            "computed_date": None,
            "excluded_deposits": 0,
        }

    rows = (
        db.query(BenchmarkResultModel)
        .filter(
            BenchmarkResultModel.account_id == account_id,
            BenchmarkResultModel.computed_date == latest_date,
        )
        .all()
    )

    defaults_map = {d["id"]: d["name"] for d in _get_defaults()}
    customs = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(BenchmarkCustomSchemeModel.account_id == account_id)
        .all()
    )
    custom_map = {str(cs.id): cs.name for cs in customs}

    portfolio_xirr = None
    portfolio_value_usd = None
    schemes = []
    for row in rows:
        if row.bench_id == _PORTFOLIO_BENCH_ID:
            portfolio_xirr = row.xirr
            portfolio_value_usd = row.current_value_usd
        else:
            name = (
                defaults_map.get(row.bench_id)
                or custom_map.get(row.bench_id)
                or row.bench_id
            )
            schemes.append(
                {
                    "id": row.bench_id,
                    "name": name,
                    "xirr": row.xirr,
                    "current_value_usd": row.current_value_usd,
                }
            )

    return {
        "portfolio_xirr": portfolio_xirr,
        "portfolio_value_usd": portfolio_value_usd,
        "schemes": schemes,
        "computed_date": latest_date,
        "excluded_deposits": 0,
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
    return _build_results_response(db, account_id)


@router.post("/compute/{account_id}", response_model=BenchmarkResultResponse)
def compute_benchmark(
    account_id: int,
    db: Session = Depends(get_db),
):
    """Compute benchmark results for an account.

    Skips computation if a valid result already exists today (portfolio xirr is
    non-NULL). The price_history layer fetches today's price once (STALE_DAYS=0)
    so the first compute of the day gets an intraday price; subsequent same-day
    calls return the cached result quickly.
    """
    _get_account_or_404(db, account_id)
    from fin.services.benchmark_service import (
        compute as benchmark_compute,
        has_recent_result,
    )

    if has_recent_result(db, account_id):
        return _build_results_response(db, account_id)

    try:
        result = benchmark_compute(db, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


@router.post("/backfill/{account_id}")
def trigger_backfill(account_id: int, db: Session = Depends(get_db)):
    """Trigger historical benchmark backfill for an account (runs synchronously)."""
    _get_account_or_404(db, account_id)
    from fin.services.benchmark_history_service import backfill_account

    written = backfill_account(db, account_id)
    return {"written": written}


@router.put("/schemes/{account_id}")
def update_schemes(
    account_id: int, payload: SchemesPayload, db: Session = Depends(get_db)
):
    """Update which default schemes are enabled for an account."""
    account = _get_account_or_404(db, account_id)

    default_ids = {d["id"] for d in _get_defaults()}
    unknown = [i for i in payload.enabled_defaults if i not in default_ids]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown default scheme IDs: {unknown}",
        )

    schemes_json = json.dumps({"enabled_defaults": payload.enabled_defaults})
    account.benchmark_schemes = schemes_json
    db.commit()
    return {"enabled_defaults": payload.enabled_defaults}


# ── Custom scheme CRUD ────────────────────────────────────────────────────────


@router.get("/custom-schemes/{account_id}")
def list_custom_schemes(account_id: int, db: Session = Depends(get_db)):
    """List all custom schemes for an account."""
    _get_account_or_404(db, account_id)
    rows = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(BenchmarkCustomSchemeModel.account_id == account_id)
        .order_by(BenchmarkCustomSchemeModel.id)
        .all()
    )
    return [_cs_to_dict(r) for r in rows]


@router.post("/custom-schemes/{account_id}", status_code=201)
def create_custom_scheme(
    account_id: int, payload: CustomSchemePayload, db: Session = Depends(get_db)
):
    """Create a custom benchmark scheme for an account."""
    _get_account_or_404(db, account_id)
    _validate_scheme_payload(payload)
    row = BenchmarkCustomSchemeModel(
        account_id=account_id,
        name=payload.name,
        allocations_json=json.dumps(
            [{"symbol": a.symbol, "pct": a.pct} for a in payload.allocations]
        ),
        cash_pct=payload.cash_pct,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _cs_to_dict(row)


@router.put("/custom-schemes/{account_id}/{scheme_id}")
def update_custom_scheme(
    account_id: int,
    scheme_id: int,
    payload: CustomSchemePayload,
    db: Session = Depends(get_db),
):
    """Update a custom benchmark scheme."""
    _get_account_or_404(db, account_id)
    row = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.id == scheme_id,
            BenchmarkCustomSchemeModel.account_id == account_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Custom scheme not found")
    _validate_scheme_payload(payload)
    old_allocs = row.allocations_json
    row.name = payload.name
    row.allocations_json = json.dumps(
        [{"symbol": a.symbol, "pct": a.pct} for a in payload.allocations]
    )
    row.cash_pct = payload.cash_pct
    db.commit()
    # If allocations changed, historical results are stale — wipe them so the
    # history chart only shows data computed with the current allocations.
    if old_allocs != row.allocations_json:
        db.query(BenchmarkResultModel).filter(
            BenchmarkResultModel.account_id == account_id,
            BenchmarkResultModel.bench_id == str(scheme_id),
        ).delete()
        db.commit()
    db.refresh(row)
    return _cs_to_dict(row)


@router.delete("/custom-schemes/{account_id}/{scheme_id}")
def delete_custom_scheme(
    account_id: int, scheme_id: int, db: Session = Depends(get_db)
):
    """Delete a custom benchmark scheme."""
    _get_account_or_404(db, account_id)
    row = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.id == scheme_id,
            BenchmarkCustomSchemeModel.account_id == account_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Custom scheme not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


class EnabledPayload(BaseModel):
    enabled: int


@router.patch("/custom-schemes/{account_id}/{scheme_id}/enabled")
def set_custom_scheme_enabled(
    account_id: int,
    scheme_id: int,
    payload: EnabledPayload,
    db: Session = Depends(get_db),
):
    """Enable or disable a custom benchmark scheme."""
    _get_account_or_404(db, account_id)
    row = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.id == scheme_id,
            BenchmarkCustomSchemeModel.account_id == account_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Custom scheme not found")
    row.enabled = 1 if payload.enabled else 0
    db.commit()
    return _cs_to_dict(row)


# ── History ───────────────────────────────────────────────────────────────────


@router.get("/history/{account_id}")
def get_history(
    account_id: int,
    since: str = Query(
        None, description="Start date YYYY-MM-DD; defaults to 1 year ago"
    ),
    db: Session = Depends(get_db),
):
    """Return historical XIRR time series grouped by bench_id.

    Granularity is 'month' when range >= 90 days, 'day' otherwise.
    """
    _get_account_or_404(db, account_id)

    if since is None:
        # Default to the earliest data available for this account
        earliest = (
            db.query(func.min(BenchmarkResultModel.computed_date))
            .filter(BenchmarkResultModel.account_id == account_id)
            .scalar()
        )
        since = earliest or str(
            (datetime.now(timezone.utc) - timedelta(days=365)).date()
        )

    try:
        datetime.strptime(since, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Invalid since date format, use YYYY-MM-DD"
        )

    today = datetime.now(timezone.utc).date()
    rows = (
        db.query(BenchmarkResultModel)
        .filter(
            BenchmarkResultModel.account_id == account_id,
            BenchmarkResultModel.computed_date >= since,
        )
        .order_by(BenchmarkResultModel.computed_date.asc())
        .all()
    )

    # Base granularity on actual data spread, not query range.
    # Until 90 days of data accumulate, daily dates are more readable.
    if rows:
        earliest_result = datetime.strptime(rows[0].computed_date, "%Y-%m-%d").date()
        data_days = (today - earliest_result).days
    else:
        data_days = 0
    granularity = "month" if data_days >= 90 else "day"

    by_bench: dict[str, list] = {}
    for row in rows:
        by_bench.setdefault(row.bench_id, []).append(
            {"date": row.computed_date, "xirr": row.xirr}
        )

    if granularity == "month":
        for key in by_bench:
            monthly: dict[str, Optional[float]] = {}
            for entry in by_bench[key]:
                monthly[entry["date"][:7]] = entry["xirr"]  # last wins (sorted asc)
            by_bench[key] = [{"date": k, "xirr": v} for k, v in sorted(monthly.items())]

    defaults_map = {d["id"]: d["name"] for d in _get_defaults()}
    customs = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(BenchmarkCustomSchemeModel.account_id == account_id)
        .all()
    )
    custom_map = {str(cs.id): cs.name for cs in customs}

    def bench_name(bid: str) -> str:
        if bid == _PORTFOLIO_BENCH_ID:
            return "Portfolio"
        return defaults_map.get(bid) or custom_map.get(bid) or bid

    order_map: dict[str, int] = {_PORTFOLIO_BENCH_ID: -1}
    for i, d in enumerate(_get_defaults()):
        order_map[d["id"]] = i

    series = sorted(
        [
            {"id": bid, "name": bench_name(bid), "data": data}
            for bid, data in by_bench.items()
        ],
        key=lambda s: order_map.get(s["id"], 999),
    )

    return {"granularity": granularity, "series": series}


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
