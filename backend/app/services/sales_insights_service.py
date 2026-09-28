"""Sales Insights analytics — SQL aggregations for Visualizations & Analytics."""

from __future__ import annotations

import re
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
    fy_short,
    fy_short_display,
    fy_start_for_calendar_month,
    month_label,
    months_for_fy_quarter,
    parse_month_label,
    parse_quarter_label,
    quarter_of_month,
)
from app.core.logging import get_logger
from app.services.analytics_aggregation import AnalyticsFilter, align_quantities, log_integrity
from app.utils.quantity import format_mt, kg_to_mt_display, round_mt

logger = get_logger(__name__)


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


def _period_year_months(
    period: Optional[str],
    *,
    fiscal_year_start: Optional[int] = None,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    as_of: Optional[date] = None,
) -> Optional[List[Tuple[int, int]]]:
    """Calendar months in the selected period. None = unrestricted; [] = match nothing."""
    period_key = (period or "").strip().lower().replace(" ", "_").replace("-", "_")
    if period_key in {"", "all"}:
        return None

    today = as_of or date.today()
    if period_key == PERIOD_LAST_3:
        return _last_n_rolling(3, as_of=today)
    if period_key == PERIOD_LAST_6:
        return _last_n_rolling(6, as_of=today)
    if period_key == PERIOD_LAST_12:
        return _last_n_rolling(12, as_of=today)

    fy_start = _normalize_fy_start(fiscal_year_start, as_of=today)
    if period_key in {PERIOD_FULL_YEAR, "full_financial_year", "fy"}:
        return fy_calendar_months(fy_start)
    if period_key in _QUARTER_PERIODS:
        pairs: List[Tuple[int, int]] = []
        for label in months_for_fy_quarter(fy_start, _QUARTER_PERIODS[period_key]):
            parsed = parse_month_label(label)
            if parsed:
                month, year = parsed
                pairs.append((year, month))
        return pairs
    if period_key in {PERIOD_CUSTOM, "custom_date_range", "custom_range"}:
        start = _parse_ym(start_month)
        end = _parse_ym(end_month)
        if not start or not end:
            return []
        if start > end:
            start, end = end, start
        pairs = []
        y, m = start
        while (y, m) <= end:
            pairs.append((y, m))
            y, m = _shift_month(y, m, 1)
        return pairs
    return None


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
    pairs = _period_year_months(
        period,
        fiscal_year_start=fiscal_year_start,
        start_month=start_month,
        end_month=end_month,
        as_of=as_of,
    )
    if pairs is None:
        return None
    if not pairs:
        return []
    keys = _keys_for_year_months(pairs)
    period_key = (period or "").strip().lower().replace(" ", "_").replace("-", "_")
    if period_key in {PERIOD_FULL_YEAR, "full_financial_year", "fy"}:
        fy_start = _normalize_fy_start(fiscal_year_start, as_of=as_of)
        keys.extend([fy_short(fy_start), fy_short_display(fy_start)])
    expanded: List[str] = []
    for label in keys:
        expanded.append(label)
        if "-" in label:
            expanded.append(label.replace("-", "–"))
        if "–" in label:
            expanded.append(label.replace("–", "-"))
        if "•" in label:
            expanded.append(label.replace("•", "·"))
            expanded.append(label.replace(" • ", " "))
    return list(dict.fromkeys(expanded))


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


_SHORT_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


_MONTH_TOKEN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_FLEX_MONTH_RE = re.compile(
    rf"(?i)(?:(\d{{1,2}})[-/\s]+)?({_MONTH_TOKEN})[a-z]*[-/\s,]*(\d{{2,4}})?"
)
_YM_RE = re.compile(r"^\s*(\d{4})[-/](\d{1,2})\s*$")
_MONTH_NUMBER = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _coerce_year(raw: Optional[str], fallback: Optional[int] = None) -> Optional[int]:
    if not raw:
        return fallback
    year = int(raw)
    if year < 100:
        year += 2000
    if 1990 <= year <= 2100:
        return year
    return fallback


def _parse_flexible_month(text: Optional[str]) -> Optional[Tuple[int, Optional[int]]]:
    """Return ``(month, year-or-None)`` for April 2026, Apr-26, 01-Apr-26, 2026-04."""
    raw = str(text or "").strip()
    if not raw:
        return None
    labeled = parse_month_label(raw)
    if labeled:
        month, year = labeled
        return month, year
    ym = _YM_RE.match(raw)
    if ym:
        year = int(ym.group(1))
        month = int(ym.group(2))
        if 1 <= month <= 12:
            return month, year
    match = _FLEX_MONTH_RE.search(raw)
    if not match:
        return None
    month = _MONTH_NUMBER[match.group(2).lower()[:3]]
    return month, _coerce_year(match.group(3))


def _fy_year_of_text(text: Optional[str]) -> Optional[int]:
    spec = parse_quarter_label(str(text or "").strip())
    if spec and spec.kind == "year" and spec.year:
        return int(spec.year)
    return None


def _quarter_of_text(text: Optional[str]) -> Optional[Tuple[int, int]]:
    spec = parse_quarter_label(str(text or "").strip())
    if spec and spec.kind == "quarter" and spec.year and spec.quarter:
        return int(spec.year), int(spec.quarter)
    return None


def _month_from_submission(
    source_month: Optional[str],
    report_name: Optional[str],
    period: Optional[str] = None,
    reporting_month: Optional[str] = None,
) -> Optional[Tuple[int, int]]:
    """Resolve a calendar month from source month, period, or the email subject."""
    quarter = _quarter_of_text(reporting_month) or _quarter_of_text(period)
    for candidate in (source_month, period, reporting_month):
        parsed = _parse_flexible_month(candidate)
        if not parsed:
            continue
        month, year = parsed
        if year is None and quarter:
            year = calendar_year_for_fy_month(quarter[0], month)
        if year is not None:
            return year, month
    if not report_name:
        return None
    from app.utils.email_subject_parser import try_parse_email_subject

    subject = try_parse_email_subject(str(report_name))
    if not subject or not subject.get("source_month"):
        return None
    parsed = _parse_flexible_month(str(subject["source_month"]))
    if not parsed or parsed[1] is None:
        return None
    month, year = parsed
    return int(year), month


def _align_month_to_window(
    key: Tuple[int, int],
    allowed: Optional[set],
    reporting_month: Optional[str],
    period: Optional[str],
) -> Optional[Tuple[int, int]]:
    """Keep a month inside the selected FY window, correcting a drifted calendar year."""
    if allowed is None or key in allowed:
        return key
    quarter = _quarter_of_text(reporting_month) or _quarter_of_text(period)
    if not quarter:
        return None
    for year, month in allowed:
        if month != key[1]:
            continue
        if fy_start_for_calendar_month(month, year) == quarter[0] and quarter_of_month(month) == quarter[1]:
            return year, month
    return None


def _spread_kg(totals: Dict[Tuple[int, int], float], slots: List[Tuple[int, int]], qty: float) -> None:
    """Split kilograms across months. The last month receives the remainder."""
    if not slots or qty == 0:
        return
    remaining = Decimal(str(qty))
    share = remaining / Decimal(len(slots))
    for index, slot in enumerate(slots):
        part = remaining if index == len(slots) - 1 else min(share, remaining)
        totals[slot] = totals.get(slot, 0.0) + float(part)
        remaining -= part


def _month_trend_points(
    rows: List[Tuple[Optional[str], Optional[str], Optional[str], Optional[str], float]],
    window: Optional[List[Tuple[int, int]]],
) -> List[Dict[str, Any]]:
    """
    Monthly sales points for every filtered record.

    A zero month stays on the chart. The series is empty only when the
    filtered row set itself is empty.
    """
    if not rows:
        return []
    allowed = set(window) if window is not None else None
    totals: Dict[Tuple[int, int], float] = {}
    exact: set = set()
    unassigned: Dict[Tuple[int, int], float] = {}
    unassigned_years: Dict[int, float] = {}
    quarters: set = set()
    for source_month, report_name, period, reporting_month, qty in rows:
        if qty < 0:
            continue
        key = _month_from_submission(source_month, report_name, period, reporting_month)
        if key:
            key = _align_month_to_window(key, allowed, reporting_month, period)
        if key:
            totals[key] = totals.get(key, 0.0) + qty
            exact.add(key)
            fy = fy_start_for_calendar_month(key[1], key[0])
            quarters.add((fy, quarter_of_month(key[1])))
            continue
        quarter = _quarter_of_text(reporting_month) or _quarter_of_text(period)
        if quarter:
            quarters.add(quarter)
            unassigned[quarter] = unassigned.get(quarter, 0.0) + qty
            continue
        fy_year = _fy_year_of_text(reporting_month) or _fy_year_of_text(period)
        if fy_year:
            unassigned_years[fy_year] = unassigned_years.get(fy_year, 0.0) + qty

    def _in_window(year: int, month: int) -> bool:
        return allowed is None or (year, month) in allowed

    for fy_start, quarter in quarters:
        for label in months_for_fy_quarter(fy_start, quarter):
            parsed = parse_month_label(label)
            if not parsed:
                continue
            month, year = parsed
            if not _in_window(year, month):
                continue
            totals.setdefault((year, month), 0.0)

    if unassigned:
        for (fy_start, quarter), qty in unassigned.items():
            slots = []
            for label in months_for_fy_quarter(fy_start, quarter):
                parsed = parse_month_label(label)
                if not parsed:
                    continue
                month, year = parsed
                if _in_window(year, month):
                    slots.append((year, month))
            _spread_kg(totals, slots, qty)

    if unassigned_years:
        for fy_start, qty in unassigned_years.items():
            slots = [
                (year, month)
                for year, month in fy_calendar_months(fy_start)
                if _in_window(year, month)
            ]
            _spread_kg(totals, slots, qty)

    if window:
        for year, month in window:
            totals.setdefault((year, month), 0.0)

    points: List[Dict[str, Any]] = []
    ordered = list(window) if window else sorted(totals)
    for year, month in ordered:
        short = _SHORT_MONTHS[month - 1]
        points.append(
            {
                "month": short,
                "tooltip": f"{short} {year}",
                "kg": totals[(year, month)],
                "qty": 0.0,
                "quantity": 0.0,
                "unit": "MT",
            }
        )
    return points


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
        return self.sales._apply_filters(
            q,
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

    def _with_filter(self, query, filt: AnalyticsFilter, **scope_kw):
        """Dimension filters plus the shared financial-year / period predicate."""
        scoped = self._scoped(
            query,
            distributor_id=None,
            month_keys=None,
            **scope_kw,
        )
        return filt.restrict(scoped)

    def sales_insights(
        self,
        *,
        distributor_id: Optional[int] = None,
        distributor: Optional[str] = None,
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
        filt = AnalyticsFilter(
            financial_year=fiscal_year_start,
            period=period,
            distributor_id=distributor_id,
            distributor=distributor,
            customer=customer,
            product=product,
            location=location,
            segment=segment,
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
            customer=customer,
            product=product,
            location=location,
            segment=segment,
            search=search,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        kpi_q = self._with_filter(
            select(
                func.coalesce(func.sum(SalesRecord.quantity), 0),
                func.count(func.distinct(SalesRecord.customer_name)),
                func.count(func.distinct(SalesRecord.product)),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id),
            filt,
            **scope_kw,
        )
        total_kg, total_customers, total_products = self.db.execute(kpi_q).one()
        total_kg_f = _to_float(total_kg)
        total_qty_f = kg_to_mt_display(total_kg_f)
        n_quarters = max(len(axis_months), 1)
        avg_monthly = total_qty_f / n_quarters

        trend_q = self._with_filter(
            select(
                SalesRecord.source_month,
                Report.name,
                SalesRecord.period,
                Report.reporting_month,
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .group_by(
                SalesRecord.source_month,
                Report.name,
                SalesRecord.period,
                Report.reporting_month,
            ),
            filt,
            **scope_kw,
        )
        monthly_trend = _month_trend_points(
            [
                (src, name, period_value, reporting_month, _to_float(qty))
                for src, name, period_value, reporting_month, qty in self.db.execute(trend_q).all()
            ],
            filt.month_window(),
        )
        placed_kg = sum(float(point["kg"]) for point in monthly_trend)
        gap = total_kg_f - placed_kg
        if monthly_trend and abs(gap) > 0.001:
            logger.warning(
                "Monthly trend was missing {:.3f} KG from the filtered total; assigned to the latest month",
                gap,
            )
            monthly_trend[-1]["kg"] = float(monthly_trend[-1]["kg"]) + gap
        month_mt = align_quantities(
            [float(point["kg"]) for point in monthly_trend],
            total_kg=total_kg_f,
        )
        for point, qty in zip(monthly_trend, month_mt):
            point["qty"] = qty
            point["quantity"] = qty
            point.pop("kg", None)

        top_q = self._with_filter(
            select(
                SalesRecord.customer_name,
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .group_by(SalesRecord.customer_name)
            .order_by(func.sum(SalesRecord.quantity).desc()),
            filt,
            **scope_kw,
        )
        customer_kg = [
            {"customer": str(name), "kg": _to_float(qty_kg)}
            for name, qty_kg in self.db.execute(top_q).all()
            if name
        ]
        if len(customer_kg) > 10:
            others_kg = sum(row["kg"] for row in customer_kg[10:])
            customer_kg = customer_kg[:10]
            if others_kg:
                customer_kg.append({"customer": "Others", "kg": others_kg})
        covered_customers = sum(row["kg"] for row in customer_kg)
        customer_gap = total_kg_f - covered_customers
        if customer_gap > 0.001:
            others = next((row for row in customer_kg if row["customer"] == "Others"), None)
            if others is None:
                customer_kg.append({"customer": "Others", "kg": customer_gap})
            else:
                others["kg"] += customer_gap
        customer_mt = align_quantities([row["kg"] for row in customer_kg], total_kg=total_kg_f)
        top_customers = [
            {"customer": row["customer"], "qty": qty, "quantity": qty, "unit": "MT"}
            for row, qty in zip(customer_kg, customer_mt)
        ]

        prod_q = self._with_filter(
            select(
                SalesRecord.product,
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .group_by(SalesRecord.product)
            .order_by(func.sum(SalesRecord.quantity).desc()),
            filt,
            **scope_kw,
        )
        prod_kg = [
            {"product": str(name), "kg": _to_float(qty_kg)}
            for name, qty_kg in self.db.execute(prod_q).all()
            if name
        ]
        top_n = 8
        if len(prod_kg) > top_n:
            others_kg = sum(row["kg"] for row in prod_kg[top_n:])
            prod_kg = prod_kg[:top_n]
            if others_kg:
                prod_kg.append({"product": "Others", "kg": others_kg})
        covered_products = sum(row["kg"] for row in prod_kg)
        product_gap = total_kg_f - covered_products
        if product_gap > 0.001:
            others = next((row for row in prod_kg if row["product"] == "Others"), None)
            if others is None:
                prod_kg.append({"product": "Others", "kg": product_gap})
            else:
                others["kg"] += product_gap
        product_mt = align_quantities([row["kg"] for row in prod_kg], total_kg=total_kg_f)
        product_contribution = [
            {"product": row["product"], "qty": qty, "quantity": qty, "unit": "MT"}
            for row, qty in zip(prod_kg, product_mt)
        ]
        log_integrity(
            kpi=total_qty_f,
            monthly=monthly_trend,
            products=product_contribution,
            customers=top_customers,
        )

        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 25), 1), 200)
        count_q = self._with_filter(
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id),
            filt,
            **scope_kw,
        )
        total_rows = int(self.db.scalar(count_q) or 0)

        rows_q = self._with_filter(
            select(
                SalesRecord.customer_name,
                SalesRecord.product,
                SalesRecord.location,
                reporting_month_expr().label("month"),
                SalesRecord.quantity.label("qty"),
                company_expr().label("distributor"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .order_by(SalesRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size),
            filt,
            **scope_kw,
        )
        table_rows = []
        for customer_name, product_name, location, month, qty_kg, distributor in self.db.execute(rows_q).all():
            quantity_mt = kg_to_mt_display(qty_kg)
            table_rows.append(
                {
                    "customer": str(customer_name or ""),
                    "product": str(product_name or ""),
                    "location": str(location or ""),
                    "month": format_period_display(str(month or "")),
                    "qty": quantity_mt,
                    "qty_display": format_mt(quantity_mt),
                    "quantity": quantity_mt,
                    "unit": "MT",
                    "distributor": str(distributor or ""),
                }
            )

        return {
            "kpis": {
                "total_sales_mt": total_qty_f,
                "total_sales_mt_display": format_mt(total_qty_f),
                "total_customers": int(total_customers or 0),
                "total_products": int(total_products or 0),
                "avg_monthly_sales_mt": round_mt(avg_monthly),
                "avg_monthly_sales_mt_display": format_mt(avg_monthly),
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
        distributor: Optional[str] = None,
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
        filt = AnalyticsFilter(
            financial_year=fiscal_year_start,
            period=period,
            distributor_id=distributor_id,
            distributor=distributor,
            customer=customer,
            product=product,
            location=location,
            segment=segment,
            start_month=start_month,
            end_month=end_month,
        )
        scope_kw = dict(
            customer=customer,
            product=product,
            location=location,
            segment=segment,
            search=search,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        rows_q = self._with_filter(
            select(
                SalesRecord.customer_name,
                SalesRecord.product,
                SalesRecord.location,
                reporting_month_expr().label("month"),
                SalesRecord.quantity.label("qty"),
                company_expr().label("distributor"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .order_by(SalesRecord.id.desc())
            .limit(limit),
            filt,
            **scope_kw,
        )
        return [
            {
                "Customer Name": str(c or ""),
                "Product": str(p or ""),
                "Location": str(loc or ""),
                "Quarter": format_period_display(str(m or "")),
                "Sales Quantity (MT)": kg_to_mt_display(q),
                "Distributor": str(d or ""),
            }
            for c, p, loc, m, q, d in self.db.execute(rows_q).all()
        ]
