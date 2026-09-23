"""Sales record repository."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import distinct, false, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.distributor import Distributor
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.repositories.base import BaseRepository


def company_expr():
    """
    Primary business entity label: Distributor Company.

    Falls back to representative name only when company is blank (legacy rows).
    """
    return func.coalesce(
        func.nullif(func.trim(Distributor.company), ""),
        Distributor.name,
    )


def reporting_month_expr():
    """Canonical reporting month: report header first, sales.period fallback."""
    return func.coalesce(
        func.nullif(func.trim(Report.reporting_month), ""),
        SalesRecord.period,
    )


class SalesRecordRepository(BaseRepository[SalesRecord]):
    """Data access for sales records and aggregations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, SalesRecord)

    def _base_query(self):
        """
        Active sales belonging to an ACTIVE report only.

        Business rule: Consolidated Data / Dashboard / Analytics must never include
        soft-deleted reports or orphan sales without a report.
        Soft-deleted distributors are excluded; null distributor_id orphans are kept
        for list views only (aggregations use ``_active_distributor_sales_where``).
        """
        return (
            select(SalesRecord)
            .options(
                selectinload(SalesRecord.distributor),
                selectinload(SalesRecord.report),
            )
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
        )

    @staticmethod
    def _active_report_sales_where():
        """Shared WHERE: active sales + active parent report (no orphans)."""
        return (
            SalesRecord.is_deleted.is_(False),
            Report.is_deleted.is_(False),
        )

    @staticmethod
    def _active_distributor_sales_where():
        """ACTIVE sales + report + non-deleted distributor (shared qty universe)."""
        return (
            SalesRecord.is_deleted.is_(False),
            Report.is_deleted.is_(False),
            Distributor.is_deleted.is_(False),
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
        location: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        distributor_id: Optional[int] = None,
        month_keys: Optional[List[str]] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ):
        """Apply dynamic filters (all optional, combinable)."""
        if allowed_segments is not None:
            if not allowed_segments:
                query = query.where(false())
            else:
                lowered = [s.casefold() for s in allowed_segments if (s or "").strip()]
                query = query.where(func.lower(SalesRecord.segment).in_(lowered))
        if allowed_companies is not None:
            if not allowed_companies:
                query = query.where(false())
            else:
                lowered_c = [c.casefold() for c in allowed_companies if (c or "").strip()]
                query = query.where(
                    or_(
                        func.lower(company_expr()).in_(lowered_c),
                        func.lower(func.coalesce(Distributor.company, "")).in_(lowered_c),
                        func.lower(func.coalesce(Distributor.name, "")).in_(lowered_c),
                    )
                )
        if distributor_id:
            query = query.where(SalesRecord.distributor_id == distributor_id)
        if distributor and distributor.lower() != "all":
            # Match company_expr label (preferred) or raw company / representative
            term = distributor.strip().lower()
            query = query.where(
                or_(
                    func.lower(company_expr()) == term,
                    func.lower(Distributor.company) == term,
                    func.lower(Distributor.name) == term,
                )
            )
        if customer and customer.lower() != "all":
            query = query.where(func.lower(SalesRecord.customer_name) == customer.strip().lower())
        if segment and segment.lower() != "all":
            query = query.where(func.lower(SalesRecord.segment) == segment.strip().lower())
        if product and product.lower() != "all":
            query = query.where(func.lower(SalesRecord.product) == product.strip().lower())
        if location and location.lower() != "all":
            term = location.strip().lower()
            effective_location = func.lower(
                func.coalesce(
                    func.nullif(func.trim(SalesRecord.location), ""),
                    func.nullif(func.trim(Distributor.region), ""),
                    "",
                )
            )
            query = query.where(effective_location == term)
        if month_keys is not None:
            if not month_keys:
                query = query.where(false())
            else:
                query = query.where(reporting_month_expr().in_(month_keys))
        if company and company.lower() != "all":
            term = company.strip().lower()
            query = query.where(func.lower(company_expr()) == term)
        if period and period.lower() != "all":
            query = query.where(reporting_month_expr() == period)
        if quarter and quarter.lower() != "all":
            # Prefer structured FY quarter labels; fall back to legacy substring
            from app.utils.period_calendar import parse_quarter_label

            spec = parse_quarter_label(quarter.strip())
            if spec:
                query = query.where(reporting_month_expr().in_(spec.month_list))
            else:
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
                    func.lower(SalesRecord.customer_name).like(term),
                    func.lower(SalesRecord.segment).like(term),
                    func.lower(SalesRecord.product).like(term),
                    func.lower(func.coalesce(SalesRecord.location, "")).like(term),
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
        location: Optional[str] = None,
        company: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        sort_by: str = "id",
        sort_dir: str = "asc",
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
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
            location=location,
            company=company,
            period=period,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
            distributor_id=distributor_id,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        sort_map = {
            "id": SalesRecord.id,
            "srNo": SalesRecord.sr_no,
            "customerName": SalesRecord.customer_name,
            "segment": SalesRecord.segment,
            "product": SalesRecord.product,
            "location": SalesRecord.location,
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

    def _filtered_from_clause(self):
        """Sales + ACTIVE report + optional distributor join (shared list/aggregate base)."""
        return (
            select(SalesRecord.id)
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                *self._active_report_sales_where(),
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
        )

    def count_filtered(
        self,
        *,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        product: Optional[str] = None,
        location: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        distributor_id: Optional[int] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> int:
        """Count rows matching the same filters as list_with_distributor."""
        query = (
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                *self._active_report_sales_where(),
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
        )
        query = self._apply_filters(
            query,
            search=search,
            distributor=distributor,
            customer=customer,
            segment=segment,
            product=product,
            location=location,
            company=company,
            period=period,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
            distributor_id=distributor_id,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        return int(self.db.scalar(query) or 0)

    def count_matching_reports(
        self,
        *,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        product: Optional[str] = None,
        location: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        distributor_id: Optional[int] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> int:
        """Count distinct ACTIVE reports matching the same filters as list."""
        query = (
            select(func.count(distinct(SalesRecord.report_id)))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                *self._active_report_sales_where(),
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
        )
        query = self._apply_filters(
            query,
            search=search,
            distributor=distributor,
            customer=customer,
            segment=segment,
            product=product,
            location=location,
            company=company,
            period=period,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
            distributor_id=distributor_id,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        return int(self.db.scalar(query) or 0)

    def list_matching_report_ids(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        product: Optional[str] = None,
        location: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        distributor_id: Optional[int] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[int]:
        """
        Paginate by complete reports (newest reporting period first).

        Avoids mid-report row cuts that hide distributors under a quarter.
        """
        period_col = reporting_month_expr()
        query = (
            select(
                SalesRecord.report_id.label("report_id"),
                func.max(period_col).label("period_label"),
                func.max(func.coalesce(Report.created_at, SalesRecord.created_at)).label("imported_at"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                *self._active_report_sales_where(),
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
            .group_by(SalesRecord.report_id)
        )
        query = self._apply_filters(
            query,
            search=search,
            distributor=distributor,
            customer=customer,
            segment=segment,
            product=product,
            location=location,
            company=company,
            period=period,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
            distributor_id=distributor_id,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        query = query.order_by(
            func.max(period_col).desc().nulls_last(),
            func.max(func.coalesce(Report.created_at, SalesRecord.created_at)).desc().nulls_last(),
            SalesRecord.report_id.desc(),
        )
        query = query.offset(max(0, skip)).limit(max(1, limit))
        return [int(row.report_id) for row in self.db.execute(query).all() if row.report_id is not None]

    def list_for_report_ids(
        self,
        report_ids: Sequence[int],
        *,
        sort_by: str = "id",
        sort_dir: str = "asc",
    ) -> List[SalesRecord]:
        """Load all active sales rows for the given report ids (complete reports)."""
        ids = [int(r) for r in report_ids if r is not None]
        if not ids:
            return []
        query = self._base_query().where(SalesRecord.report_id.in_(ids))
        sort_map = {
            "id": SalesRecord.id,
            "srNo": SalesRecord.sr_no,
            "customerName": SalesRecord.customer_name,
            "segment": SalesRecord.segment,
            "product": SalesRecord.product,
            "quantity": SalesRecord.quantity,
            "period": SalesRecord.period,
            "reportingMonth": SalesRecord.period,
            "distributor": Distributor.name,
            "importedAt": SalesRecord.created_at,
        }
        col = sort_map.get(sort_by, SalesRecord.id)
        query = query.order_by(col.desc() if sort_dir.lower() == "desc" else col.asc())
        rows = list(self.db.scalars(query).unique().all())
        # Preserve report pagination order
        order = {rid: idx for idx, rid in enumerate(ids)}
        rows.sort(key=lambda r: (order.get(r.report_id, 10**9), r.id or 0))
        return rows

    def period_summaries(
        self,
        *,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        product: Optional[str] = None,
        location: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        distributor_id: Optional[int] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Accurate per-period rollups for the full filtered set (not the current page).

        Used so quarter headers never under-count distributors due to pagination.
        """
        period_col = reporting_month_expr()
        company_col = company_expr()
        query = (
            select(
                period_col.label("period"),
                func.count(distinct(SalesRecord.report_id)).label("report_count"),
                func.count(distinct(func.lower(company_col))).label("distributor_count"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                *self._active_report_sales_where(),
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
                period_col.is_not(None),
                period_col != "",
            )
            .group_by(period_col)
            .order_by(period_col.desc())
        )
        query = self._apply_filters(
            query,
            search=search,
            distributor=distributor,
            customer=customer,
            segment=segment,
            product=product,
            location=location,
            company=company,
            period=period,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
            distributor_id=distributor_id,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        out: List[Dict[str, Any]] = []
        for row in self.db.execute(query).all():
            label = str(row.period or "").strip()
            if not label:
                continue
            out.append(
                {
                    "label": label,
                    "reportCount": int(row.report_count or 0),
                    "distributorCount": int(row.distributor_count or 0),
                    "totalQuantity": float(row.qty or 0),
                }
            )
        return out

    def count_by_distributor_period(self, distributor_name: str, period: str) -> int:
        """Count active sales for distributor company/name + reporting month."""
        term = distributor_name.strip().lower()
        query = (
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                *self._active_distributor_sales_where(),
                or_(
                    func.lower(company_expr()) == term,
                    func.lower(Distributor.company) == term,
                    func.lower(Distributor.name) == term,
                ),
                reporting_month_expr() == period,
            )
        )
        return int(self.db.scalar(query) or 0)

    def soft_delete_by_distributor_period(self, distributor_name: str, period: str) -> Tuple[int, List[int]]:
        """
        Soft-delete all sales rows for distributor company/name + reporting month.

        Matches ``company_expr`` / company / name and canonical reporting month.
        Returns ``(rows_deleted, affected_report_ids)``.
        """
        term = distributor_name.strip().lower()
        query = (
            select(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                *self._active_distributor_sales_where(),
                or_(
                    func.lower(company_expr()) == term,
                    func.lower(Distributor.company) == term,
                    func.lower(Distributor.name) == term,
                ),
                reporting_month_expr() == period,
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

    def distinct_column_values(self, column_name: str) -> List[str]:
        """SELECT DISTINCT for a known sales/distributor column (generic filter engine)."""
        # Prefer report-level Reporting Month for period filters
        if column_name in {"period", "quarter", "reporting_month"}:
            query = (
                select(distinct(Report.reporting_month))
                .select_from(SalesRecord)
                .join(Report, Report.id == SalesRecord.report_id)
                .where(
                    *self._active_report_sales_where(),
                    Report.reporting_month.is_not(None),
                    Report.reporting_month != "",
                )
                .order_by(Report.reporting_month.asc())
            )
            values = [str(row) for row in self.db.scalars(query).all() if row]
            if values:
                return values
            # Fallback to denormalized sales.period for legacy rows under active reports
            query = (
                select(distinct(SalesRecord.period))
                .join(Report, Report.id == SalesRecord.report_id)
                .where(
                    *self._active_report_sales_where(),
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
            "location": SalesRecord.location,
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
                .join(Report, Report.id == SalesRecord.report_id)
                .where(
                    *self._active_report_sales_where(),
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
                .join(Report, Report.id == SalesRecord.report_id)
                .where(
                    *self._active_report_sales_where(),
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

    def total_quantity(
        self,
        *,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> Decimal:
        """Sum of quantities from ACTIVE reports + ACTIVE distributors only."""
        query = (
            select(func.coalesce(func.sum(SalesRecord.quantity), 0))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(*self._active_distributor_sales_where())
        )
        query = self._apply_filters(
            query,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        return Decimal(str(self.db.scalar(query) or 0))

    def count_contributing_reports(self) -> int:
        """Distinct ACTIVE reports that contribute at least one ACTIVE sales row."""
        query = (
            select(func.count(distinct(Report.id)))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(*self._active_distributor_sales_where())
        )
        return int(self.db.scalar(query) or 0)

    def product_quantities(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Aggregate quantity by product (ACTIVE reports + distributors only)."""
        query = (
            select(
                SalesRecord.product.label("product"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(*self._active_distributor_sales_where())
            .group_by(SalesRecord.product)
            .order_by(func.sum(SalesRecord.quantity).desc())
        )
        query = self._apply_viz_filters(
            query,
            period=period,
            product=product,
            distributor=distributor,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        rows = self.db.execute(query).all()
        return [{"product": row.product, "qty": float(row.qty)} for row in rows]

    def distributor_totals(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Aggregate quantity per Distributor Company (ACTIVE reports only)."""
        entity = company_expr().label("name")
        query = (
            select(
                entity,
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
                func.count(distinct(SalesRecord.customer_name)).label("customers"),
                func.count(distinct(SalesRecord.product)).label("products"),
                func.count(SalesRecord.id).label("orders"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                *self._active_report_sales_where(),
                Distributor.is_deleted.is_(False),
            )
            .group_by(entity)
            .order_by(func.sum(SalesRecord.quantity).desc())
        )
        query = self._apply_viz_filters(
            query,
            period=period,
            product=product,
            distributor=distributor,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
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

    def count_active_with_parents(self) -> int:
        """Count sales rows whose parent report and distributor are active."""
        query = (
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(*self._active_distributor_sales_where())
        )
        return int(self.db.scalar(query) or 0)

    def monthly_sales_trend(
        self,
        *,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Quantity by reporting quarter from ACTIVE reports.

        Prefers Report.reporting_month, falls back to SalesRecord.period.
        Response keys: ``month`` (legacy) and ``quarter`` (preferred) — same value.
        """
        month_expr = reporting_month_expr()
        query = (
            select(
                month_expr.label("month"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                *self._active_distributor_sales_where(),
                month_expr.is_not(None),
                month_expr != "",
            )
            .group_by(month_expr)
        )
        query = self._apply_viz_filters(
            query,
            product=product,
            distributor=distributor,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        rows = self.db.execute(query).all()
        results = [
            {
                "month": str(row.month),
                "quarter": str(row.month),
                "qty": float(row.qty),
            }
            for row in rows
            if row.month
        ]
        return _sort_reporting_months(results)

    def distributor_month_matrix(
        self,
        *,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        distributor_limit: int = 20,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Heatmap matrix: distributors × months → quantity (ACTIVE reports).

        Returns {months, distributors, cells: [{distributor, month, qty}]}.
        """
        month_expr = func.coalesce(Report.reporting_month, SalesRecord.period)
        # Limit to top distributor companies by total qty (keeps heatmap readable)
        top = self.distributor_totals(
            product=product,
            distributor=distributor,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        top_names = [r["name"] for r in top[: max(1, distributor_limit)]]
        if not top_names:
            return {"months": [], "distributors": [], "cells": []}

        entity = company_expr()
        query = (
            select(
                entity.label("distributor"),
                month_expr.label("month"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                *self._active_report_sales_where(),
                Distributor.is_deleted.is_(False),
                entity.in_(top_names),
                month_expr.is_not(None),
                month_expr != "",
            )
            .group_by(entity, month_expr)
        )
        query = self._apply_viz_filters(
            query,
            product=product,
            distributor=distributor,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        rows = self.db.execute(query).all()
        cells = [
            {"distributor": row.distributor, "month": str(row.month), "qty": float(row.qty)}
            for row in rows
            if row.month
        ]
        month_set = {c["month"] for c in cells}
        months_sorted = [m["month"] for m in _sort_reporting_months([{"month": m, "qty": 0} for m in month_set])]
        # Preserve top-company order
        return {"months": months_sorted, "distributors": top_names, "cells": cells}

    @staticmethod
    def _apply_viz_filters(
        query,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ):
        """Optional exact filters for visualization endpoints."""
        if allowed_segments is not None:
            if not allowed_segments:
                query = query.where(false())
            else:
                lowered = [s.casefold() for s in allowed_segments if (s or "").strip()]
                query = query.where(func.lower(SalesRecord.segment).in_(lowered))
        if allowed_companies is not None:
            if not allowed_companies:
                query = query.where(false())
            else:
                lowered_c = [c.casefold() for c in allowed_companies if (c or "").strip()]
                query = query.where(
                    or_(
                        func.lower(company_expr()).in_(lowered_c),
                        func.lower(func.coalesce(Distributor.company, "")).in_(lowered_c),
                        func.lower(func.coalesce(Distributor.name, "")).in_(lowered_c),
                    )
                )
        if period and period.lower() != "all":
            query = query.where(reporting_month_expr() == period)
        if product and product.lower() != "all":
            query = query.where(func.lower(SalesRecord.product) == product.strip().lower())
        if distributor and distributor.lower() != "all":
            term = distributor.strip().lower()
            query = query.where(
                or_(
                    func.lower(company_expr()) == term,
                    func.lower(Distributor.company) == term,
                    func.lower(Distributor.name) == term,
                )
            )
        return query

    def distributor_product_mix(
        self,
        products: Optional[List[str]] = None,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        distributor_limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Pivot quantity by Distributor Company and product (optional Top-N companies)."""
        entity = company_expr()
        query = (
            select(
                entity.label("distributor"),
                SalesRecord.product.label("product"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(*self._active_distributor_sales_where())
            .group_by(entity, SalesRecord.product)
        )
        query = self._apply_viz_filters(
            query, period=period, product=product, distributor=distributor
        )
        if products:
            query = query.where(SalesRecord.product.in_(products))

        rows = self.db.execute(query).all()
        pivot: Dict[str, Dict[str, Any]] = {}
        product_set = products or sorted({row.product for row in rows})
        company_totals: Dict[str, float] = {}
        for row in rows:
            entry = pivot.setdefault(
                row.distributor,
                {"distributor": row.distributor, **{p: 0.0 for p in product_set}},
            )
            qty = float(row.qty)
            entry[row.product] = qty
            company_totals[row.distributor] = company_totals.get(row.distributor, 0.0) + qty

        ordered = sorted(pivot.values(), key=lambda r: company_totals.get(r["distributor"], 0.0), reverse=True)
        if distributor_limit and distributor_limit > 0:
            return ordered[:distributor_limit]
        return ordered

    def distinct_products(self) -> List[str]:
        """Return sorted distinct product names."""
        return self.distinct_column_values("product")

    def distinct_periods(self) -> List[str]:
        """Return sorted distinct periods."""
        return self.distinct_column_values("period")

    def distinct_distributors_with_sales(self) -> List[str]:
        """Distributor Company names that have ACTIVE sales (matches Consolidated)."""
        entity = company_expr().label("company")
        query = (
            select(entity)
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                *self._active_report_sales_where(),
                Distributor.is_deleted.is_(False),
                entity.is_not(None),
                entity != "",
            )
            .distinct()
            .order_by(entity.asc())
        )
        return [str(row.company) for row in self.db.execute(query).all() if row.company]

    def quarterly_company_summary(
        self,
        months: Sequence[str],
        *,
        company: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        SQL aggregation: one row per Distributor Company for the given months.

        ACTIVE reports only. No in-memory rollup of full report payloads.
        """
        if not months:
            return []
        entity = company_expr()
        month_expr = func.coalesce(Report.reporting_month, SalesRecord.period)
        query = (
            select(
                entity.label("company"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
                func.count(distinct(SalesRecord.product)).label("products"),
                func.count(distinct(SalesRecord.customer_name)).label("customers"),
                func.count(distinct(Report.id)).label("reports"),
                func.string_agg(distinct(month_expr), ",").label("months_csv"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                *self._active_report_sales_where(),
                Distributor.is_deleted.is_(False),
                month_expr.in_(list(months)),
            )
            .group_by(entity)
            .order_by(func.sum(SalesRecord.quantity).desc())
        )
        if company and company.lower() != "all":
            query = query.where(func.lower(company_expr()) == company.strip().lower())

        rows = self.db.execute(query).all()
        results: List[Dict[str, Any]] = []
        for row in rows:
            raw_months = [m for m in str(row.months_csv or "").split(",") if m]
            # Preserve quarter month order
            ordered = [m for m in months if m in raw_months]
            for m in raw_months:
                if m not in ordered:
                    ordered.append(m)
            results.append(
                {
                    "company": row.company,
                    "qty": float(row.qty or 0),
                    "products": int(row.products or 0),
                    "customers": int(row.customers or 0),
                    "reports": int(row.reports or 0),
                    "months": ordered,
                }
            )
        return results

    def _quarter_company_where(self, months: Sequence[str], company: str):
        """Shared ACTIVE filters for company + quarter months."""
        return (
            *self._active_distributor_sales_where(),
            func.lower(company_expr()) == company.strip().lower(),
            reporting_month_expr().in_(list(months)),
        )

    def quarterly_customer_detail(
        self,
        months: Sequence[str],
        *,
        company: str,
        search: Optional[str] = None,
        sort_by: str = "quantity",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Customer × Segment × Product SQL aggregation for one company + quarter.

        Filtering, sorting, and pagination run in the database.
        Contribution % uses the full quarter total (search does not change the denominator).
        """
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 10), 100))
        empty = {
            "items": [],
            "totalRecords": 0,
            "totalPages": 0,
            "currentPage": page,
            "pageSize": page_size,
            "quarterTotalQty": 0.0,
        }
        if not months or not company:
            return empty

        scope = self._quarter_company_where(months, company)

        # Full-quarter total for Contribution % (never filtered by search)
        total_q = (
            select(func.coalesce(func.sum(SalesRecord.quantity), 0))
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(*scope)
        )
        quarter_total = float(self.db.scalar(total_q) or 0)

        qty_expr = func.coalesce(func.sum(SalesRecord.quantity), 0)
        grouped = (
            select(
                SalesRecord.customer_name.label("customer"),
                SalesRecord.segment.label("segment"),
                SalesRecord.product.label("product"),
                qty_expr.label("qty"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(*scope)
        )

        term = (search or "").strip()
        if term:
            pattern = f"%{term}%"
            grouped = grouped.where(
                or_(
                    SalesRecord.customer_name.ilike(pattern),
                    SalesRecord.segment.ilike(pattern),
                    SalesRecord.product.ilike(pattern),
                )
            )

        grouped = grouped.group_by(
            SalesRecord.customer_name,
            SalesRecord.segment,
            SalesRecord.product,
        )

        subq = grouped.subquery("q_detail")
        total_records = int(
            self.db.scalar(select(func.count()).select_from(subq)) or 0
        )
        total_pages = (total_records + page_size - 1) // page_size if total_records else 0
        if total_pages and page > total_pages:
            page = total_pages

        sort_key = (sort_by or "quantity").strip().lower().replace("-", "").replace("_", "").replace("%", "")
        sort_cols = {
            "customer": subq.c.customer,
            "segment": subq.c.segment,
            "product": subq.c.product,
            "quantity": subq.c.qty,
            "qty": subq.c.qty,
            "contribution": subq.c.qty,
            "contributionpct": subq.c.qty,
        }
        order_col = sort_cols.get(sort_key, subq.c.qty)
        descending = (sort_order or "desc").strip().lower() != "asc"
        order_expr = order_col.desc() if descending else order_col.asc()
        secondary = (subq.c.customer.asc(), subq.c.product.asc())

        offset = (page - 1) * page_size
        page_q = (
            select(subq.c.customer, subq.c.segment, subq.c.product, subq.c.qty)
            .order_by(order_expr, *secondary)
            .offset(offset)
            .limit(page_size)
        )
        rows = self.db.execute(page_q).all()

        items: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            qty = float(row.qty or 0)
            items.append(
                {
                    "srNo": offset + idx + 1,
                    "customer": row.customer or "",
                    "segment": row.segment or "",
                    "product": row.product or "",
                    "quantity": qty,
                    "contributionPct": (
                        round((qty / quarter_total) * 100, 2) if quarter_total else 0.0
                    ),
                }
            )

        return {
            "items": items,
            "totalRecords": total_records,
            "totalPages": total_pages,
            "currentPage": page,
            "pageSize": page_size,
            "quarterTotalQty": quarter_total,
        }

    def quarterly_product_breakdown(
        self,
        months: Sequence[str],
        *,
        company: str,
    ) -> List[Dict[str, Any]]:
        """Legacy product rollup — prefer ``quarterly_customer_detail`` for detail UI."""
        if not months or not company:
            return []
        query = (
            select(
                SalesRecord.product.label("product"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
                func.count(distinct(SalesRecord.customer_name)).label("customers"),
            )
            .select_from(SalesRecord)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(*self._quarter_company_where(months, company))
            .group_by(SalesRecord.product)
            .order_by(func.sum(SalesRecord.quantity).desc())
        )
        rows = self.db.execute(query).all()
        total = sum(float(r.qty or 0) for r in rows) or 0.0
        return [
            {
                "product": row.product,
                "qty": float(row.qty or 0),
                "customers": int(row.customers or 0),
                "contributionPct": round((float(row.qty or 0) / total) * 100, 2) if total else 0.0,
            }
            for row in rows
        ]

    def count_active_for_report(self, report_id: int) -> int:
        """Count non-deleted sales rows for a report."""
        query = select(func.count(SalesRecord.id)).where(
            SalesRecord.report_id == report_id,
            SalesRecord.is_deleted.is_(False),
        )
        return int(self.db.scalar(query) or 0)


_MONTH_ORDER = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _sort_reporting_months(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort period labels (``FY 2025-26 • Q1`` or ``March 2024``) chronologically when possible."""
    import re

    from app.utils.period_calendar import quarter_of_month

    def key(item: Dict[str, Any]):
        label = str(item.get("month") or item.get("quarter") or "")
        qmatch = re.match(r"^\s*Q([1-4])\s+(\d{4})\s*$", label, flags=re.IGNORECASE)
        if qmatch:
            return (int(qmatch.group(2)), int(qmatch.group(1)), label.lower())
        match = re.match(r"^\s*([A-Za-z]+)\s+(\d{4})\s*$", label)
        if match:
            month_name, year = match.group(1).lower(), int(match.group(2))
            month_num = _MONTH_ORDER.get(month_name, 99)
            return (year, quarter_of_month(month_num) if month_num <= 12 else 99, label.lower())
        return (9999, 99, label.lower())

    return sorted(rows, key=key)
