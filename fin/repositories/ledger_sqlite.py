from collections import defaultdict
from datetime import date, timedelta
from datetime import datetime as dt
from datetime import timezone

from sqlalchemy.orm import Session

from fin.models.ledger import LedgerModel
from fin.schemas.ledger import LedgerCreate, LedgerUpdate


class LedgerSQLiteRepository:
    """SQLite-backed repository for ledger (income + expense) records."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_list(
        self,
        user_id: int,
        direction: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        category: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[LedgerModel], int]:
        """Return a paginated, filtered list and total count."""
        from sqlalchemy import or_

        q = self._db.query(LedgerModel).filter(LedgerModel.user_id == user_id)
        if direction:
            q = q.filter(LedgerModel.direction == direction)
        if start_date:
            q = q.filter(LedgerModel.date >= start_date)
        if end_date:
            q = q.filter(LedgerModel.date <= end_date)
        if category:
            q = q.filter(LedgerModel.category == category)
        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    LedgerModel.name.ilike(like),
                    LedgerModel.note.ilike(like),
                    LedgerModel.category.ilike(like),
                    LedgerModel.subcategory.ilike(like),
                    LedgerModel.orig_category.ilike(like),
                )
            )
        total = q.count()
        items = (
            q.order_by(LedgerModel.date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_by_id(self, id: int, user_id: int) -> LedgerModel | None:
        return (
            self._db.query(LedgerModel)
            .filter(LedgerModel.id == id, LedgerModel.user_id == user_id)
            .first()
        )

    def get_years(self, user_id: int) -> list[int]:
        """Return distinct years that have ledger entries, most recent first."""
        from sqlalchemy import func

        rows = (
            self._db.query(func.substr(LedgerModel.date, 1, 4))
            .filter(LedgerModel.user_id == user_id)
            .distinct()
            .all()
        )
        return sorted([int(r[0]) for r in rows], reverse=True)

    def get_recurring(
        self, user_id: int, include_expired: bool = False
    ) -> list[tuple[LedgerModel, int]]:
        """Return recurring items deduplicated by (recurring_type, category, subcategory).

        Amount is intentionally not part of the key — a recurring expense whose
        price fluctuates (e.g. monthly utility bills) stays one series. The latest
        record's amount is shown as the representative value.

        Each entry is paired with the total occurrence count of its series.
        A series is considered expired when its most recent record has is_expired=True.
        subcategory is guaranteed non-null for recurring rows (initialized at create
        time via repo.create() and backfilled by _backfill_recurring_subcategory).

        Args:
            user_id: Owning user.
            include_expired: When True, returns only expired series; when False, only active.

        Returns:
            List of (latest_record, count) tuples.
        """
        rows = (
            self._db.query(LedgerModel)
            .filter(
                LedgerModel.user_id == user_id,
                LedgerModel.recurring_type.isnot(None),
            )
            .order_by(LedgerModel.date.desc())
            .all()
        )
        grouped: dict[tuple, list[LedgerModel]] = {}
        for r in rows:
            key = (r.recurring_type, r.category, r.subcategory)
            grouped.setdefault(key, []).append(r)

        result: list[tuple[LedgerModel, int]] = []
        for group in grouped.values():
            latest = group[0]  # already sorted desc
            if bool(latest.is_expired) != bool(include_expired):
                continue
            result.append((latest, len(group)))
        return result

    def get_series(
        self,
        user_id: int,
        recurring_type: str,
        category: str,
        subcategory: str,
    ) -> list[LedgerModel]:
        """Return all records belonging to a recurring series, newest first.

        Series identity matches get_recurring's dedup key.
        """
        return (
            self._db.query(LedgerModel)
            .filter(
                LedgerModel.user_id == user_id,
                LedgerModel.recurring_type == recurring_type,
                LedgerModel.category == category,
                LedgerModel.subcategory == subcategory,
            )
            .order_by(LedgerModel.date.desc())
            .all()
        )

    def get_stats(
        self,
        user_id: int,
        time_range: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        category: str | None = None,
    ) -> dict:
        """Aggregate stats for charts and summary tiles.

        time_range and start_date/end_date are mutually exclusive:
        - time_range drives bar chart + pie (absolute recency window)
        - start_date/end_date drives summary tiles (year-level totals)
        """
        today = date.today()

        if time_range:
            if time_range == "7d":
                q_start = (today - timedelta(days=6)).isoformat()
                q_end = today.isoformat()
            elif time_range == "30d":
                q_start = (today - timedelta(days=29)).isoformat()
                q_end = today.isoformat()
            elif time_range == "all":
                q_start, q_end = None, None
            else:  # 1y
                q_start = date(today.year - 1, today.month, today.day).isoformat()
                q_end = today.isoformat()
        else:
            q_start, q_end = start_date, end_date

        q = self._db.query(LedgerModel).filter(LedgerModel.user_id == user_id)
        if q_start:
            q = q.filter(LedgerModel.date >= q_start)
        if q_end:
            q = q.filter(LedgerModel.date <= q_end)
        if category:
            q = q.filter(LedgerModel.category == category)

        rows = q.all()

        # Summary
        income_total = sum(r.amount for r in rows if r.direction == "income")
        expense_rows = [r for r in rows if r.direction == "expense"]
        expense_total = sum(r.amount for r in expense_rows)
        max_expense = max((r.amount for r in expense_rows), default=0.0)

        # Bar granularity: yearly for "all", monthly when window > 60 days
        if time_range == "all":
            yearly, monthly = True, False
        elif time_range == "1y":
            yearly, monthly = False, True
        elif time_range in ("7d", "30d"):
            yearly, monthly = False, False
        elif q_start and q_end:
            delta = date.fromisoformat(q_end) - date.fromisoformat(q_start)
            yearly, monthly = False, delta.days > 60
        else:
            yearly, monthly = False, False

        # Bar chart — expense only
        by_bucket: dict[str, float] = defaultdict(float)
        for r in expense_rows:
            if yearly:
                bucket = r.date[:4]
            elif monthly:
                bucket = r.date[:7]
            else:
                bucket = r.date
            by_bucket[bucket] += r.amount
        bars = [
            {"date": k, "amount": round(v, 2)} for k, v in sorted(by_bucket.items())
        ]

        # Pie — expense by category
        by_cat: dict[str, float] = defaultdict(float)
        for r in expense_rows:
            by_cat[r.category] += r.amount
        pie = [
            {"category": k, "amount": round(v, 2)}
            for k, v in sorted(by_cat.items(), key=lambda x: -x[1])
        ]

        return {
            "bars": bars,
            "pie": pie,
            "summary": {
                "income": round(income_total, 2),
                "expense": round(expense_total, 2),
                "net": round(income_total - expense_total, 2),
                "max_expense": round(max_expense, 2),
            },
        }

    def create(self, data: LedgerCreate, user_id: int) -> LedgerModel:
        # For recurring items, default subcategory to name so dedup has a stable key
        subcategory = data.subcategory
        if data.recurring_type and not subcategory:
            subcategory = data.name
        entry = LedgerModel(
            user_id=user_id,
            direction=data.direction,
            name=data.name,
            date=data.date,
            amount=data.amount,
            currency=data.currency,
            category=data.category,
            orig_category=data.orig_category,
            subcategory=subcategory,
            recurring_type=data.recurring_type,
            is_expired=data.is_expired,
            expiry_date=data.expiry_date,
            note=data.note,
        )
        self._db.add(entry)
        self._db.commit()
        self._db.refresh(entry)
        return entry

    def update(self, id: int, data: LedgerUpdate, user_id: int) -> LedgerModel:
        entry = self.get_by_id(id, user_id)
        if entry is None:
            raise ValueError(f"Ledger entry {id} not found")
        for field, val in data.model_dump(exclude_unset=True).items():
            setattr(entry, field, val)
        entry.update_time = dt.now(timezone.utc)
        self._db.commit()
        self._db.refresh(entry)
        return entry

    def delete(self, id: int, user_id: int) -> None:
        entry = self.get_by_id(id, user_id)
        if entry:
            self._db.delete(entry)
            self._db.commit()

    def rename_category(self, user_id: int, old_name: str, new_name: str) -> int:
        """Bulk-update category column when a custom category is renamed.

        Returns the number of rows updated. Built-in renames don't reach this
        path because built-ins are immutable from the API.
        """
        from sqlalchemy import update as sql_update

        result = self._db.execute(
            sql_update(LedgerModel)
            .where(LedgerModel.user_id == user_id)
            .where(LedgerModel.category == old_name)
            .values(category=new_name)
        )
        self._db.commit()
        return result.rowcount

    def bulk_create(self, items: list[LedgerCreate], user_id: int) -> list[LedgerModel]:
        """Bulk-insert records, skipping exact duplicates."""
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        now = dt.now(timezone.utc)
        inserted_ids: list[int] = []
        for d in items:
            stmt = (
                sqlite_insert(LedgerModel)
                .values(
                    user_id=user_id,
                    direction=d.direction,
                    name=d.name,
                    date=d.date,
                    amount=d.amount,
                    currency=d.currency,
                    category=d.category,
                    orig_category=d.orig_category,
                    subcategory=d.subcategory,
                    recurring_type=d.recurring_type,
                    is_expired=d.is_expired,
                    expiry_date=d.expiry_date,
                    note=d.note,
                    create_time=now,
                    update_time=now,
                )
                .on_conflict_do_nothing()
            )
            result = self._db.execute(stmt)
            if result.rowcount:
                inserted_ids.append(result.inserted_primary_key[0])
        self._db.commit()
        if not inserted_ids:
            return []
        return (
            self._db.query(LedgerModel).filter(LedgerModel.id.in_(inserted_ids)).all()
        )
