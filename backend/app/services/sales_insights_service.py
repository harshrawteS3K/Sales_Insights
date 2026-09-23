"""Sales Insights analytics — SQL aggregations for Visualizations & Analytics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models.distributor import Distributor
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.repositories.sales_record_repository import (
    SalesRecordRepository,
    company_expr,
    reporting_month_expr,
)
from app.utils.period_calendar import (
    calendar_year_for_fy_month,
    format_period_display,
    fy_quarter_label,
    fy_short_display,
    fy_start_for_calendar_month,
    month_label,
    months_for_fy_quarter,
    parse_month_label,
    quarter_of_month,
)
from app.utils.quantity import format_quantity
from app.utils.reporting_month import normalize_reporting_month


PERIOD_FULL_YEAR = "full_year"
PERIOD_Q1 = "q1"
PERIOD_Q2 = "q2"
PERIOD_Q3 = "q3"
PERIOD_Q4 = "q4"
PERIOD_LAST_3 = "last_3_months"
PERIOD_LAST_6 = "last_6_months"
PERIOD_LAST_12 = "last_12_months"
PERIOD_CUSTOM = "custom"

_PERIOD_MONTH_COUNT = {
    PERIOD_LAST_3: 3,
    PERIOD_LAST_6: 6,
    PERIOD_LAST_12: 12,
}

_QUARTER_PERIODS = {
    PERIOD_Q1: 1,
    PERIOD_Q2: 2,
    PERIOD_Q3: 3,
    PERIOD_Q4: 4,
}

# Fixed Financial Year options for the Visualizations filter
_FY_FILTER_STARTS = (2024, 2025, 2026)

_ROLLING_PERIODS = {PERIOD_LAST_3, PERIOD_LAST_6, PERIOD_LAST_12}
_FY_REQUIRED_PERIODS = {PERIOD_FULL_YEAR, PERIOD_Q1, PERIOD_Q2, PERIOD_Q3, PERIOD_Q4}


def _to_float(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except Exception:  # noqa: BLE001
        return 0.0


def _shift_month(year: int, month: int, delta: int) -> Tuple[int, int]:
    d = date(year, month, 1) + relativedelta(months=delta)
    return d.year, d.month


def _keys_for_calendar_month(year: int, month: int) -> List[str]:
    """Match month labels and Indian FY quarter keys for that calendar month."""
    q = quarter_of_month(month)
    fy_start = fy_start_for_calendar_month(month, year)
    return [
        month_label(month, year),
        fy_quarter_label(fy_start, q),
        f"Q{q} {fy_start}",  # legacy FY-start year key
    ]


def _parse_ym(raw: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse ``YYYY-MM`` or ``January 2026`` → (year, month)."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    if len(text) >= 7 and text[4] == "-":
        try:
            y = int(text[:4])
            m = int(text[5:7])
            if 1 <= m <= 12:
                return y, m
        except ValueError:
            pass
    parsed = parse_month_label(text)
    if parsed:
        month, year = parsed
        return year, month
    return None


def _normalize_fy_start(
    fiscal_year_start: Optional[int], *, as_of: Optional[date] = None
) -> int:
    if fiscal_year_start and 1990 <= int(fiscal_year_start) <= 2100:
        return int(fiscal_year_start)
    return _fallback_fy_start(as_of)


def _fallback_fy_start(today: Optional[date] = None) -> int:
    d = today or date.today()
    return d.year if d.month >= 4 else d.year - 1


def fy_calendar_months(fy_start: int) -> List[Tuple[int, int]]:
    """Apr (fy_start) … Mar (fy_start+1) as ``(year, month)`` tuples."""
    out: List[Tuple[int, int]] = []
    for m in (4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3):
        out.append((calendar_year_for_fy_month(fy_start, m), m))
    return out


def _keys_for_year_months(pairs: List[Tuple[int, int]]) -> List[str]:
    keys: List[str] = []
    for y, m in pairs:
        keys.extend(_keys_for_calendar_month(y, m))
    return list(dict.fromkeys(keys))


def _quarter_labels_for_pairs(pairs: List[Tuple[int, int]]) -> List[str]:
    """One canonical FY-quarter label per distinct quarter, oldest → newest."""
    labels: List[str] = []
    for year, month in pairs:
        label = fy_quarter_label(
            fy_start_for_calendar_month(month, year),
            quarter_of_month(month),
        )
        if not labels or labels[-1] != label:
            labels.append(label)
    return labels


def _last_n_within_fy(
    fy_start: int, n: int, *, as_of: Optional[date] = None
) -> List[Tuple[int, int]]:
    """Last N months within the selected FY, anchored to today when inside the FY."""
    today = as_of or date.today()
    fy_months = fy_calendar_months(fy_start)
    fy_begin = date(fy_start, 4, 1)
    fy_end = date(fy_start + 1, 3, 31)
    if today < fy_begin:
        return fy_months[:n]
    if today > fy_end:
        return fy_months[-n:]
    current = (today.year, today.month)
    available = [ym for ym in fy_months if ym <= current]
    return available[-n:] if available else []


def _last_n_rolling(n: int, *, as_of: Optional[date] = None) -> List[Tuple[int, int]]:
    """Last N calendar months ending at as_of (inclusive), oldest → newest."""
    today = as_of or date.today()
    out: List[Tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(max(1, int(n))):
        out.append((y, m))
        y, m = _shift_month(y, m, -1)
    out.reverse()
    return out


def resolve_period_month_keys(
    period: Optional[str],
    *,
    fiscal_year_start: Optional[int] = None,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    as_of: Optional[date] = None,
) -> Optional[List[str]]:
    """
    Resolve reporting_month keys for the selected FY + period filter.

    Returns None = no period restriction; [] = invalid range (match nothing).
    Rolling periods ignore fiscal_year_start. Custom range uses From/To months.
    """
    period_key = (period or "").strip().lower().replace(" ", "_").replace("-", "_")
    if period_key in {"", "all"}:
        return None

    today = as_of or date.today()

    if period_key in _PERIOD_MONTH_COUNT:
        n = _PERIOD_MONTH_COUNT[period_key]
        return _keys_for_year_months(_last_n_rolling(n, as_of=today))

    fy_start = _normalize_fy_start(fiscal_year_start)

    if period_key in {PERIOD_FULL_YEAR, "full_financial_year", "fy"}:
        return _keys_for_year_months(fy_calendar_months(fy_start))

    if period_key in _QUARTER_PERIODS:
        q = _QUARTER_PERIODS[period_key]
        pairs = []
        for label in months_for_fy_quarter(fy_start, q):
            parsed = parse_month_label(label)
            if parsed:
                month, year = parsed
                pairs.append((year, month))
        return _keys_for_year_months(pairs)

    if period_key in {PERIOD_CUSTOM, "custom_date_range", "custom_range"}:
        start = _parse_ym(start_month)
        end = _parse_ym(end_month)
        if not start or not end:
            return []
        if start > end:
            start, end = end, start
        keys: List[str] = []
        y, m = start
        while (y, m) <= end:
            keys.extend(_keys_for_calendar_month(y, m))
            y, m = _shift_month(y, m, 1)
        return list(dict.fromkeys(keys))

    return None


def trend_month_labels(
    period: Optional[str],
    *,
    fiscal_year_start: Optional[int] = None,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    as_of: Optional[date] = None,
) -> List[str]:
    """Ordered FY-quarter labels for the trend chart (one point per quarter)."""
    period_key = (period or "").strip().lower().replace(" ", "_").replace("-", "_")
    today = as_of or date.today()

    if period_key in _PERIOD_MONTH_COUNT:
        n = _PERIOD_MONTH_COUNT[period_key]
        return _quarter_labels_for_pairs(_last_n_rolling(n, as_of=today))

    fy_start = _normalize_fy_start(fiscal_year_start)

    if period_key in {PERIOD_FULL_YEAR, "full_financial_year", "fy"}:
        return _quarter_labels_for_pairs(fy_calendar_months(fy_start))

    if period_key in _QUARTER_PERIODS:
        return [fy_quarter_label(fy_start, _QUARTER_PERIODS[period_key])]

    if period_key in {PERIOD_CUSTOM, "custom_date_range", "custom_range"}:
        start = _parse_ym(start_month)
        end = _parse_ym(end_month)
        if not start or not end:
            return []
        if start > end:
            start, end = end, start
        pairs: List[Tuple[int, int]] = []
        y, m = start
        while (y, m) <= end:
            pairs.append((y, m))
            y, m = _shift_month(y, m, 1)
        return _quarter_labels_for_pairs(pairs)

    return _quarter_labels_for_pairs(fy_calendar_months(fy_start))


class SalesInsightsService:
    """Pure SQL analytics for the Visualizations & Analytics page."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sales = SalesRecordRepository(db)

    def filter_options(
        self,
        *,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        dist_q = (
            select(Distributor.id, company_expr().label("company"))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                Distributor.is_deleted.is_(False),
            )
            .distinct()
            .order_by(company_expr().asc())
        )
        dist_q = self.sales._apply_filters(
            dist_q,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        cust_q = (
            select(distinct(SalesRecord.customer_name))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                SalesRecord.customer_name.is_not(None),
                SalesRecord.customer_name != "",
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
            .order_by(SalesRecord.customer_name.asc())
            .limit(5000)
        )
        cust_q = self.sales._apply_filters(
            cust_q,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        prod_q = (
            select(distinct(SalesRecord.product))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                SalesRecord.product.is_not(None),
                SalesRecord.product != "",
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
            .order_by(SalesRecord.product.asc())
            .limit(2000)
        )
        prod_q = self.sales._apply_filters(
            prod_q,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        loc_q = (
            select(distinct(SalesRecord.location))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                SalesRecord.location.is_not(None),
                SalesRecord.location != "",
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
            .order_by(SalesRecord.location.asc())
            .limit(500)
        )
        loc_q = self.sales._apply_filters(
            loc_q,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        seg_q = (
            select(distinct(SalesRecord.segment))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .outerjoin(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                SalesRecord.segment.is_not(None),
                SalesRecord.segment != "",
                or_(Distributor.id.is_(None), Distributor.is_deleted.is_(False)),
            )
            .order_by(SalesRecord.segment.asc())
            .limit(200)
        )
        seg_q = self.sales._apply_filters(
            seg_q,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        distributors = [
            {"id": int(r[0]), "name": (r[1] or "").strip() or f"Distributor #{r[0]}"}
            for r in self.db.execute(dist_q).all()
            if r[0] is not None
        ]
        customers = [str(c) for c in self.db.scalars(cust_q).all() if c]
        products = [str(p) for p in self.db.scalars(prod_q).all() if p]
        locations = [str(loc) for loc in self.db.scalars(loc_q).all() if loc]
        segments = [str(s) for s in self.db.scalars(seg_q).all() if s]
        return {
            "distributors": distributors,
            "customers": customers,
            "products": products,
            "locations": locations,
            "segments": segments,
            "financial_years": [
                {"value": y, "label": fy_short_display(y)} for y in _FY_FILTER_STARTS
            ],
            "periods": [
                {"value": PERIOD_FULL_YEAR, "label": "Full Financial Year"},
                {"value": PERIOD_Q1, "label": "Q1 (Apr–Jun)"},
                {"value": PERIOD_Q2, "label": "Q2 (Jul–Sep)"},
                {"value": PERIOD_Q3, "label": "Q3 (Oct–Dec)"},
                {"value": PERIOD_Q4, "label": "Q4 (Jan–Mar)"},
                {"value": PERIOD_LAST_3, "label": "Last 3 Months"},
                {"value": PERIOD_LAST_6, "label": "Last 6 Months"},
                {"value": PERIOD_LAST_12, "label": "Last 12 Months"},
                {"value": PERIOD_CUSTOM, "label": "Custom Range"},
            ],
        }

    def _scoped(
        self,
        query,
        *,
        distributor_id: Optional[int],
        customer: Optional[str],
        product: Optional[str],
        location: Optional[str],
        segment: Optional[str],
        search: Optional[str],
        month_keys: Optional[List[str]],
        allowed_segments: Optional[List[str]],
        allowed_companies: Optional[List[str]],
    ):
        q = query.where(
            SalesRecord.is_deleted.is_(False),
            Report.is_deleted.is_(False),
            Distributor.is_deleted.is_(False),
        )
        q = self.sales._apply_filters(
            q,
            distributor_id=distributor_id,
            customer=customer,
            product=product,
            location=location,
            segment=segment,
            search=search,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        if month_keys is not None:
            if not month_keys:
                q = q.where(SalesRecord.id == -1)
            else:
                q = q.where(reporting_month_expr().in_(month_keys))
        return q

    def sales_insights(
        self,
        *,
        distributor_id: Optional[int] = None,
        customer: Optional[str] = None,
        product: Optional[str] = None,
        location: Optional[str] = None,
        segment: Optional[str] = None,
        fiscal_year_start: Optional[int] = None,
        period: Optional[str] = None,
        start_month: Optional[str] = None,
        end_month: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        month_keys = resolve_period_month_keys(
            period,
            fiscal_year_start=fiscal_year_start,
            start_month=start_month,
            end_month=end_month,
        )
        axis_months = trend_month_labels(
            period,
            fiscal_year_start=fiscal_year_start,
            start_month=start_month,
            end_month=end_month,
        )
        scope_kw = dict(
            distributor_id=distributor_id,
            customer=customer,
            product=product,
            location=location,
            segment=segment,
            search=search,
            month_keys=month_keys,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        kpi_q = self._scoped(
            select(
                func.coalesce(func.sum(SalesRecord.quantity), 0),
                func.count(func.distinct(SalesRecord.customer_name)),
                func.count(func.distinct(SalesRecord.product)),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id),
            **scope_kw,
        )
        total_qty, total_customers, total_products = self.db.execute(kpi_q).one()
        total_qty_f = _to_float(total_qty)
        n_quarters = max(len(axis_months), 1)
        avg_monthly = total_qty_f / n_quarters

        trend_q = self._scoped(
            select(
                reporting_month_expr().label("month"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .group_by(reporting_month_expr()),
            **scope_kw,
        )
        collapsed_trend: Dict[str, float] = {}
        for raw_key, qty in self.db.execute(trend_q).all():
            if not raw_key:
                continue
            canon = normalize_reporting_month(raw_key) or str(raw_key)
            collapsed_trend[canon] = collapsed_trend.get(canon, 0.0) + _to_float(qty)
        monthly_trend = [
            {"month": label, "qty": round(collapsed_trend.get(label, 0.0), 3)}
            for label in axis_months
        ]

        top_q = self._scoped(
            select(
                SalesRecord.customer_name,
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .group_by(SalesRecord.customer_name)
            .order_by(func.sum(SalesRecord.quantity).desc())
            .limit(10),
            **scope_kw,
        )
        top_customers = [
            {"customer": str(c), "qty": round(_to_float(q), 3)}
            for c, q in self.db.execute(top_q).all()
            if c
        ]

        prod_q = self._scoped(
            select(
                SalesRecord.product,
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .group_by(SalesRecord.product)
            .order_by(func.sum(SalesRecord.quantity).desc()),
            **scope_kw,
        )
        prod_rows = [
            {"product": str(p), "qty": round(_to_float(q), 3)}
            for p, q in self.db.execute(prod_q).all()
            if p
        ]
        top_n = 8
        if len(prod_rows) > top_n:
            head = prod_rows[:top_n]
            others = sum(r["qty"] for r in prod_rows[top_n:])
            if others > 0:
                head.append({"product": "Others", "qty": round(others, 3)})
            product_contribution = head
        else:
            product_contribution = prod_rows

        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 25), 1), 200)
        count_q = self._scoped(
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id),
            **scope_kw,
        )
        total_rows = int(self.db.scalar(count_q) or 0)

        rows_q = self._scoped(
            select(
                SalesRecord.customer_name,
                SalesRecord.product,
                SalesRecord.location,
                reporting_month_expr().label("month"),
                SalesRecord.quantity,
                company_expr().label("distributor"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .order_by(SalesRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size),
            **scope_kw,
        )
        table_rows = [
            {
                "customer": str(c or ""),
                "product": str(p or ""),
                "location": str(loc or ""),
                "month": format_period_display(str(m or "")),
                "qty": round(_to_float(q), 3),
                "distributor": str(d or ""),
            }
            for c, p, loc, m, q, d in self.db.execute(rows_q).all()
        ]

        return {
            "kpis": {
                "total_sales_mt": round(total_qty_f, 3),
                "total_sales_mt_display": format_quantity(total_qty_f),
                "total_customers": int(total_customers or 0),
                "total_products": int(total_products or 0),
                "avg_monthly_sales_mt": round(avg_monthly, 3),
                "avg_monthly_sales_mt_display": format_quantity(avg_monthly),
            },
            "monthly_trend": monthly_trend,
            "top_customers": top_customers,
            "product_contribution": product_contribution,
            "table": {
                "rows": table_rows,
                "total": total_rows,
                "page": page,
                "page_size": page_size,
            },
            "period_months": axis_months,
        }

    def export_rows(
        self,
        *,
        distributor_id: Optional[int] = None,
        customer: Optional[str] = None,
        product: Optional[str] = None,
        location: Optional[str] = None,
        segment: Optional[str] = None,
        fiscal_year_start: Optional[int] = None,
        period: Optional[str] = None,
        start_month: Optional[str] = None,
        end_month: Optional[str] = None,
        search: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
        limit: int = 10000,
    ) -> List[Dict[str, Any]]:
        month_keys = resolve_period_month_keys(
            period,
            fiscal_year_start=fiscal_year_start,
            start_month=start_month,
            end_month=end_month,
        )
        scope_kw = dict(
            distributor_id=distributor_id,
            customer=customer,
            product=product,
            location=location,
            segment=segment,
            search=search,
            month_keys=month_keys,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        rows_q = self._scoped(
            select(
                SalesRecord.customer_name,
                SalesRecord.product,
                SalesRecord.location,
                reporting_month_expr().label("month"),
                SalesRecord.quantity,
                company_expr().label("distributor"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .order_by(SalesRecord.id.desc())
            .limit(limit),
            **scope_kw,
        )
        return [
            {
                "Customer Name": str(c or ""),
                "Product": str(p or ""),
                "Location": str(loc or ""),
                "Quarter": format_period_display(str(m or "")),
                "Sales Quantity (MT)": round(_to_float(q), 3),
                "Distributor": str(d or ""),
            }
            for c, p, loc, m, q, d in self.db.execute(rows_q).all()
        ]
