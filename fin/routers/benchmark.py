import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from fin.config import APP_CONFIG
from fin.database import get_db
from fin.models.account import AccountModel
from fin.models.benchmark_custom_scheme import BenchmarkCustomSchemeModel
from fin.models.benchmark_result import BenchmarkResultModel
from fin.models.user import MOCK_USER_ID
from fin.services.benchmark_service import _PORTFOLIO_BENCH_ID, _load_benchmark_defaults
from fin.services.price_history_service import fetch_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/benchmark")

_DEFAULT_SINCE_YEARS: int = APP_CONFIG.get("benchmark_default_since_years", 10)


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


class CustomSchemeResponse(BaseModel):
    id: str
    name: str
    allocations: list[dict]
    cash_pct: float
    enabled: int
    is_portfolio_snap: bool


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
        "is_portfolio_snap": bool(row.is_portfolio_snapshot),
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

    defaults_map = {d["id"]: d["name"] for d in _load_benchmark_defaults()}
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
    return _load_benchmark_defaults()


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
    except ValueError:
        raise HTTPException(
            status_code=404, detail="Account not found or benchmark disabled"
        )
    return result


@router.post("/backfill/{account_id}", status_code=202)
def trigger_backfill(
    account_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger historical benchmark backfill in the background (returns immediately)."""
    _get_account_or_404(db, account_id)

    def _run() -> None:
        from fin.database import SessionLocal
        from fin.services.benchmark_history_service import backfill_account

        _db = SessionLocal()
        try:
            backfill_account(_db, account_id)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.put("/schemes/{account_id}")
def update_schemes(
    account_id: int, payload: SchemesPayload, db: Session = Depends(get_db)
):
    """Update which default schemes are enabled for an account."""
    account = _get_account_or_404(db, account_id)

    default_ids = {d["id"] for d in _load_benchmark_defaults()}
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


def _sample_portfolio_snaps(snap_ids: list[str], max_total: int = 5) -> set[str]:
    """Return a sampled subset of portfolio snapshot bench_ids.

    Spreads up to max_total IDs evenly across the full period.
    snap_ids must be sorted oldest-first by integer ID.
    """
    if not snap_ids:
        return set()
    n = len(snap_ids)
    if n <= max_total:
        return set(snap_ids)
    indices = {round(i * (n - 1) / (max_total - 1)) for i in range(max_total)}
    return {snap_ids[i] for i in indices}


@router.get("/custom-schemes/{account_id}", response_model=list[CustomSchemeResponse])
def list_custom_schemes(account_id: int, db: Session = Depends(get_db)):
    """List all custom schemes for an account (excludes portfolio snapshots)."""
    _get_account_or_404(db, account_id)
    rows = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account_id,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 0,
        )
        .order_by(BenchmarkCustomSchemeModel.id)
        .all()
    )
    return [_cs_to_dict(r) for r in rows]


@router.get(
    "/portfolio-snapshots/{account_id}", response_model=list[CustomSchemeResponse]
)
def list_portfolio_snapshots(account_id: int, db: Session = Depends(get_db)):
    """List portfolio composition snapshots for an account (newest first)."""
    _get_account_or_404(db, account_id)
    rows = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(
            BenchmarkCustomSchemeModel.account_id == account_id,
            BenchmarkCustomSchemeModel.is_portfolio_snapshot == 1,
        )
        .order_by(BenchmarkCustomSchemeModel.id.desc())
        .all()
    )
    return [_cs_to_dict(r) for r in rows]


@router.post(
    "/custom-schemes/{account_id}", status_code=201, response_model=CustomSchemeResponse
)
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


@router.put(
    "/custom-schemes/{account_id}/{scheme_id}", response_model=CustomSchemeResponse
)
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
    old_cash_pct = row.cash_pct
    row.name = payload.name
    row.allocations_json = json.dumps(
        [{"symbol": a.symbol, "pct": a.pct} for a in payload.allocations]
    )
    row.cash_pct = payload.cash_pct
    db.commit()
    # If allocations or cash_pct changed, historical results are stale — wipe them.
    if old_allocs != row.allocations_json or old_cash_pct != row.cash_pct:
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


@router.patch(
    "/custom-schemes/{account_id}/{scheme_id}/enabled",
    response_model=CustomSchemeResponse,
)
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
        # Skip the first 3 months after the first result: early XIRR is
        # very noisy because a small portfolio with few deposits produces
        # extreme swings from minor price moves.
        # Cap at today so newly-enabled accounts (whose earliest = today) still
        # see their current data rather than getting an empty response.
        earliest = (
            db.query(func.min(BenchmarkResultModel.computed_date))
            .filter(BenchmarkResultModel.account_id == account_id)
            .scalar()
        )
        if earliest:
            earliest_dt = datetime.strptime(earliest, "%Y-%m-%d").date()
            skipped_dt = earliest_dt + timedelta(days=91)
            today_dt = datetime.now(timezone.utc).date()
            since = str(min(skipped_dt, today_dt))
        else:
            since = str((datetime.now(timezone.utc) - timedelta(days=365)).date())

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

    defaults_map = {d["id"]: d["name"] for d in _load_benchmark_defaults()}
    customs = (
        db.query(BenchmarkCustomSchemeModel)
        .filter(BenchmarkCustomSchemeModel.account_id == account_id)
        .all()
    )
    custom_map = {str(cs.id): cs.name for cs in customs}

    # Portfolio snapshots: sample up to 5 evenly spread across the full period
    snap_schemes = [cs for cs in customs if cs.is_portfolio_snapshot]
    snap_schemes.sort(key=lambda cs: cs.id)
    snap_id_list = [str(cs.id) for cs in snap_schemes]
    sampled_snap_ids = _sample_portfolio_snaps(snap_id_list)

    def bench_name(bid: str) -> str:
        return defaults_map.get(bid) or custom_map.get(bid) or bid

    order_map: dict[str, int] = {}
    for i, d in enumerate(_load_benchmark_defaults()):
        order_map[d["id"]] = i

    snap_id_set = set(snap_id_list)
    series_list = []
    for bid, data in by_bench.items():
        if bid in snap_id_set and bid not in sampled_snap_ids:
            continue  # unsampled portfolio snapshot
        s: dict = {"id": bid, "name": bench_name(bid), "data": data}
        if bid in sampled_snap_ids:
            snap_raw_name = custom_map.get(bid, "")
            snap_date_str = (
                snap_raw_name.split("Portfolio ", 1)[1]
                if snap_raw_name.startswith("Portfolio ")
                else ""
            )
            s["is_portfolio_snap"] = True
            s["snap_date"] = snap_date_str
        series_list.append(s)

    series = sorted(series_list, key=lambda s: order_map.get(s["id"], 999))

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
