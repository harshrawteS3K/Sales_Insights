"""Sales record repository."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import distinct, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.distributor import Distributor
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.repositories.base import BaseRepository


class SalesRecordRepository(BaseRepository[SalesRecord]):
    """Data access for sales records and aggregations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, SalesRecord)

    def _base_query(self):
        """Active sales only — never returns rows whose parent report is archived."""
        return (
            select(SalesRecord)
            .options(
                selectinload(SalesRecord.distributor),
                selectinload(SalesRecord.report),
            )
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .outerjoin(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                or_(Report.id.is_(None), Report.is_deleted.is_(False)),
            )
        )

    def _apply_filters(
        self,
        query,
        *,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        product: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        distributor_id: Optional[int] = None,
    ):
        """Apply dynamic filters (all optional, combinable)."""
        if distributor_id:
            query = query.where(SalesRecord.distributor_id == distributor_id)
        if distributor and distributor.lower() != "all":
            query = query.where(func.lower(Distributor.name) == distributor.strip().lower())
        if customer and customer.lower() != "all":
            query = query.where(func.lower(SalesRecord.customer_name) == customer.strip().lower())
        if segment and segment.lower() != "all":
            query = query.where(func.lower(SalesRecord.segment) == segment.strip().lower())
        if product and product.lower() != "all":
            query = query.where(func.lower(SalesRecord.product) == product.strip().lower())
        if company and company.lower() != "all":
            query = query.where(func.lower(Distributor.company) == company.strip().lower())
        if period and period.lower() != "all":
            query = query.where(
                or_(
                    SalesRecord.period == period,
                    Report.reporting_month == period,
                )
            )
        if quarter and quarter.lower() != "all":
            # Match reporting months / legacy period tokens (e.g. Q2)
            q = quarter.strip()
            query = query.where(
                or_(
                    SalesRecord.period.ilike(f"%{q}%"),
                    Report.reporting_month.ilike(f"%{q}%"),
                )
            )
        if quantity_min is not None:
            query = query.where(SalesRecord.quantity >= quantity_min)
        if quantity_max is not None:
            query = query.where(SalesRecord.quantity <= quantity_max)
        if imported_from is not None:
            start = datetime.combine(imported_from, datetime.min.time()).replace(tzinfo=timezone.utc)
            query = query.where(SalesRecord.created_at >= start)
        if imported_to is not None:
            end = datetime.combine(imported_to, datetime.max.time()).replace(tzinfo=timezone.utc)
            query = query.where(SalesRecord.created_at <= end)
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(Distributor.name).like(term),
                    func.lower(func.coalesce(Distributor.company, "")).like(term),
                    func.lower(func.coalesce(Distributor.address, "")).like(term),
                    func.lower(func.coalesce(Distributor.phone, "")).like(term),
                    func.lower(SalesRecord.customer_name).like(term),
                    func.lower(SalesRecord.segment).like(term),
                    func.lower(SalesRecord.product).like(term),
                    func.lower(func.coalesce(SalesRecord.period, "")).like(term),
                    func.lower(func.coalesce(Report.reporting_month, "")).like(term),
                )
            )
        return query

    def list_with_distributor(
        self,
        *,
        skip: int = 0,
        limit: int = 5000,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor_id: Optional[int] = None,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        company: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        sort_by: str = "id",
        sort_dir: str = "asc",
    ) -> List[SalesRecord]:
        """List sales records with distributor eagerly loaded and dynamic filters."""
        query = self._base_query()
        query = self._apply_filters(
            query,
            search=search,
            distributor=distributor,
            customer=customer,
            segment=segment,
            product=product,
            company=company,
            period=period,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
            distributor_id=distributor_id,
        )
        sort_map = {
            "id": SalesRecord.id,
            "srNo": SalesRecord.sr_no,
            "customerName": SalesRecord.customer_name,
            "segment": SalesRecord.segment,
            "product": SalesRecord.product,
            "openingStock": SalesRecord.opening_stock,
            "closingStock": SalesRecord.closing_stock,
            "quantity": SalesRecord.quantity,
            "period": SalesRecord.period,
            "reportingMonth": SalesRecord.period,
            "distributor": Distributor.name,
            "importedAt": SalesRecord.created_at,
        }
        col = sort_map.get(sort_by, SalesRecord.id)
        query = query.order_by(col.desc() if sort_dir.lower() == "desc" else col.asc())
        query = query.offset(skip).limit(limit)
        return list(self.db.scalars(query).unique().all())

    def count_filtered(
        self,
        *,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        product: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        distributor_id: Optional[int] = None,
    ) -> int:
        """Count rows matching the same filters as list_with_distributor."""
        query = (
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .outerjoin(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                or_(Report.id.is_(None), Report.is_deleted.is_(False)),
            )
        )
        query = self._apply_filters(
            query,
            search=search,
            distributor=distributor,
            customer=customer,
            segment=segment,
            product=product,
            company=company,
            period=period,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
            distributor_id=distributor_id,
        )
        return int(self.db.scalar(query) or 0)

    def count_by_distributor_period(self, distributor_name: str, period: str) -> int:
        """Count active sales rows for a distributor + reporting period (report unit)."""
        query = (
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Distributor.is_deleted.is_(False),
                func.lower(Distributor.name) == distributor_name.strip().lower(),
                SalesRecord.period == period,
            )
        )
        return int(self.db.scalar(query) or 0)

    def soft_delete_by_distributor_period(self, distributor_name: str, period: str) -> Tuple[int, List[int]]:
        """
        Soft-delete all sales rows for distributor + period.

        Returns ``(rows_deleted, affected_report_ids)``.
        """
        query = (
            select(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                func.lower(Distributor.name) == distributor_name.strip().lower(),
                SalesRecord.period == period,
            )
        )
        rows = list(self.db.scalars(query).all())
        now = datetime.now(timezone.utc)
        report_ids: List[int] = []
        for row in rows:
            row.is_deleted = True
            row.deleted_at = now
            if row.report_id and row.report_id not in report_ids:
                report_ids.append(row.report_id)
        self.db.flush()
        return len(rows), report_ids

    def soft_delete_for_report(self, report_id: int) -> int:
        """Soft-delete all active sales rows belonging to a report. Returns count."""
        now = datetime.now(timezone.utc)
        result = self.db.execute(
            update(SalesRecord)
            .where(
                SalesRecord.report_id == report_id,
                SalesRecord.is_deleted.is_(False),
            )
            .values(is_deleted=True, deleted_at=now)
        )
        self.db.flush()
        return int(result.rowcount or 0)

    def _active_only(self, query):
        """Restrict to sales whose parent report is active (or missing)."""
        return (
            query.outerjoin(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                or_(Report.id.is_(None), Report.is_deleted.is_(False)),
            )
        )

    def distinct_column_values(self, column_name: str) -> List[str]:
        """SELECT DISTINCT for a known sales/distributor column (generic filter engine)."""
        # Prefer report-level Reporting Month for period filters
        if column_name in {"period", "quarter", "reporting_month"}:
            query = (
                select(distinct(Report.reporting_month))
                .select_from(SalesRecord)
                .join(Report, Report.id == SalesRecord.report_id)
                .where(
                    SalesRecord.is_deleted.is_(False),
                    Report.is_deleted.is_(False),
                    Report.reporting_month.is_not(None),
                    Report.reporting_month != "",
                )
                .order_by(Report.reporting_month.asc())
            )
            values = [str(row) for row in self.db.scalars(query).all() if row]
            if values:
                return values
            # Fallback to denormalized sales.period for legacy rows
            query = (
                select(distinct(SalesRecord.period))
                .outerjoin(Report, Report.id == SalesRecord.report_id)
                .where(
                    SalesRecord.is_deleted.is_(False),
                    or_(Report.id.is_(None), Report.is_deleted.is_(False)),
                    SalesRecord.period.is_not(None),
                    SalesRecord.period != "",
                )
                .order_by(SalesRecord.period.asc())
            )
            return [str(row) for row in self.db.scalars(query).all() if row]

        column_map = {
            "customer": SalesRecord.customer_name,
            "customer_name": SalesRecord.customer_name,
            "segment": SalesRecord.segment,
            "product": SalesRecord.product,
            "distributor": Distributor.name,
            "company": Distributor.company,
        }
        col = column_map.get(column_name)
        if col is None:
            return []

        if column_name in {"distributor", "company"}:
            query = (
                select(distinct(col))
                .select_from(SalesRecord)
                .join(Distributor, Distributor.id == SalesRecord.distributor_id)
                .outerjoin(Report, Report.id == SalesRecord.report_id)
                .where(
                    SalesRecord.is_deleted.is_(False),
                    or_(Report.id.is_(None), Report.is_deleted.is_(False)),
                    Distributor.is_deleted.is_(False),
                    col.is_not(None),
                    col != "",
                )
                .order_by(col.asc())
            )
        else:
            query = (
                select(distinct(col))
                .select_from(SalesRecord)
                .outerjoin(Report, Report.id == SalesRecord.report_id)
                .where(
                    SalesRecord.is_deleted.is_(False),
                    or_(Report.id.is_(None), Report.is_deleted.is_(False)),
                    col.is_not(None),
                    col != "",
                )
                .order_by(col.asc())
            )
        return [str(row) for row in self.db.scalars(query).all() if row]

    def distinct_quarters(self) -> List[str]:
        """
        Distinct quarter tokens derived from period values (e.g. Q1, Q2 FY26 → Q2).

        Falls back to full period list when no Q# pattern is found.
        """
        import re

        periods = self.distinct_column_values("period")
        quarters: List[str] = []
        seen = set()
        for period in periods:
            match = re.search(r"\b(Q[1-4])\b", period, flags=re.IGNORECASE)
            if match:
                token = match.group(1).upper()
                if token not in seen:
                    seen.add(token)
                    quarters.append(token)
        return quarters if quarters else periods

    def exists_row_hash(self, report_id: int, row_hash: str) -> bool:
        """Check whether a row hash already exists for a report."""
        query = select(SalesRecord.id).where(
            SalesRecord.report_id == report_id,
            SalesRecord.row_hash == row_hash,
            SalesRecord.is_deleted.is_(False),
        )
        return self.db.scalar(query) is not None

    def bulk_insert(self, records: Sequence[SalesRecord]) -> int:
        """Insert many sales records and return count."""
        self.db.add_all(list(records))
        self.db.flush()
        return len(records)

    def total_quantity(self) -> Decimal:
        """Sum of all quantities from active reports only."""
        query = (
            select(func.coalesce(func.sum(SalesRecord.quantity), 0))
            .select_from(SalesRecord)
            .outerjoin(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                or_(Report.id.is_(None), Report.is_deleted.is_(False)),
            )
        )
        return Decimal(str(self.db.scalar(query) or 0))

    def product_quantities(self, *, period: Optional[str] = None) -> List[Dict[str, Any]]:
        """Aggregate quantity by product."""
        query = (
            select(
                SalesRecord.product.label("product"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .outerjoin(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                or_(Report.id.is_(None), Report.is_deleted.is_(False)),
            )
            .group_by(SalesRecord.product)
            .order_by(func.sum(SalesRecord.quantity).desc())
        )
        if period and period.lower() != "all":
            query = query.where(
                or_(SalesRecord.period == period, Report.reporting_month == period)
            )
        rows = self.db.execute(query).all()
        return [{"product": row.product, "qty": float(row.qty)} for row in rows]

    def distributor_totals(self, *, period: Optional[str] = None) -> List[Dict[str, Any]]:
        """Aggregate quantity / customers / products per distributor."""
        query = (
            select(
                Distributor.name.label("name"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
                func.count(distinct(SalesRecord.customer_name)).label("customers"),
                func.count(distinct(SalesRecord.product)).label("products"),
                func.count(SalesRecord.id).label("orders"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .outerjoin(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Distributor.is_deleted.is_(False),
                or_(Report.id.is_(None), Report.is_deleted.is_(False)),
            )
            .group_by(Distributor.name)
            .order_by(func.sum(SalesRecord.quantity).desc())
        )
        if period and period.lower() != "all":
            query = query.where(
                or_(SalesRecord.period == period, Report.reporting_month == period)
            )
        rows = self.db.execute(query).all()
        results: List[Dict[str, Any]] = []
        for row in rows:
            orders = int(row.orders or 0)
            qty = float(row.qty or 0)
            results.append(
                {
                    "name": row.name,
                    "qty": qty,
                    "customers": int(row.customers or 0),
                    "products": int(row.products or 0),
                    "avgOrder": round(qty / orders, 2) if orders else 0.0,
                }
            )
        return results

    def distributor_product_mix(
        self,
        products: Optional[List[str]] = None,
        *,
        period: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Pivot quantity by distributor and product."""
        query = (
            select(
                Distributor.name.label("distributor"),
                SalesRecord.product.label("product"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .outerjoin(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Distributor.is_deleted.is_(False),
                or_(Report.id.is_(None), Report.is_deleted.is_(False)),
            )
            .group_by(Distributor.name, SalesRecord.product)
        )
        if period and period.lower() != "all":
            query = query.where(
                or_(SalesRecord.period == period, Report.reporting_month == period)
            )
        if products:
            query = query.where(SalesRecord.product.in_(products))

        rows = self.db.execute(query).all()
        pivot: Dict[str, Dict[str, Any]] = {}
        product_set = products or sorted({row.product for row in rows})
        for row in rows:
            entry = pivot.setdefault(
                row.distributor,
                {"distributor": row.distributor, **{p: 0.0 for p in product_set}},
            )
            entry[row.product] = float(row.qty)
        return list(pivot.values())

    def distinct_products(self) -> List[str]:
        """Return sorted distinct product names."""
        return self.distinct_column_values("product")

    def distinct_periods(self) -> List[str]:
        """Return sorted distinct periods."""
        return self.distinct_column_values("period")

    def count_active_for_report(self, report_id: int) -> int:
        """Count non-deleted sales rows for a report."""
        query = select(func.count(SalesRecord.id)).where(
            SalesRecord.report_id == report_id,
            SalesRecord.is_deleted.is_(False),
        )
        return int(self.db.scalar(query) or 0)
