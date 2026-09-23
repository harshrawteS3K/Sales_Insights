"""Distributor Performance benchmarking analytics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.distributor import Distributor
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.repositories.sales_record_repository import (
    SalesRecordRepository,
    company_expr,
    reporting_month_expr,
)
from app.services.sales_insights_service import (
    PERIOD_CUSTOM,
    PERIOD_FULL_YEAR,
    PERIOD_LAST_12,
    PERIOD_LAST_3,
    PERIOD_LAST_6,
    PERIOD_Q1,
    PERIOD_Q2,
    PERIOD_Q3,
    PERIOD_Q4,
    _to_float,
    resolve_period_month_keys,
)
from app.services.distributor_service import DistributorService
from app.utils.distributor_location import country_group, country_label, normalize_location
from app.utils.quantity import format_quantity


class DistributorPerformanceService:
    """Compare directory distributors within FY / period / segment / location."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sales = SalesRecordRepository(db)

    def filter_options(
        self,
        *,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        from app.services.sales_insights_service import SalesInsightsService

        base = SalesInsightsService(self.db).filter_options(
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        # Ensure period labels match enterprise filter bar
        base["periods"] = [
            {"value": PERIOD_FULL_YEAR, "label": "Full Financial Year"},
            {"value": PERIOD_Q1, "label": "Q1 (Apr–Jun)"},
            {"value": PERIOD_Q2, "label": "Q2 (Jul–Sep)"},
            {"value": PERIOD_Q3, "label": "Q3 (Oct–Dec)"},
            {"value": PERIOD_Q4, "label": "Q4 (Jan–Mar)"},
            {"value": PERIOD_LAST_3, "label": "Last 3 Months"},
            {"value": PERIOD_LAST_6, "label": "Last 6 Months"},
            {"value": PERIOD_LAST_12, "label": "Last 12 Months"},
            {"value": PERIOD_CUSTOM, "label": "Custom Range"},
        ]
        return base

    def _directory_distributors(
        self,
        *,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Distributor]:
        q = (
            select(Distributor)
            .where(
                Distributor.is_deleted.is_(False),
                Distributor.is_active.is_(True),
            )
            .order_by(company_expr().asc(), Distributor.id.asc())
        )
        rows = list(self.db.scalars(q).all())
        if allowed_companies is None:
            return rows
        allowed = {c.casefold() for c in allowed_companies if (c or "").strip()}
        if not allowed:
            return []
        out: List[Distributor] = []
        for d in rows:
            label = ((d.company or "").strip() or (d.name or "").strip()).casefold()
            name = (d.name or "").strip().casefold()
            company = (d.company or "").strip().casefold()
            if label in allowed or name in allowed or company in allowed:
                out.append(d)
        return out

    def performance(
        self,
        *,
        fiscal_year_start: Optional[int] = None,
        period: Optional[str] = None,
        segment: Optional[str] = None,
        location: Optional[str] = None,
        country: Optional[str] = None,
        distributor_id: Optional[int] = None,
        customer: Optional[str] = None,
        product: Optional[str] = None,
        start_month: Optional[str] = None,
        end_month: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        month_keys = resolve_period_month_keys(
            period,
            fiscal_year_start=fiscal_year_start,
            start_month=start_month,
            end_month=end_month,
        )
        seg = (segment or "").strip()
        if seg.lower() == "all":
            seg = None
        DistributorService(self.db).backfill_blank_locations()
        loc = (location or "").strip()
        if loc.lower() == "all":
            loc = None
        country_key = (country or "").strip().casefold().replace(" ", "_")
        if country_key in {"", "all"}:
            country_key = ""
        elif country_key in {"other", "other_countries", "others"}:
            country_key = "other"
        elif country_key != "india":
            country_key = ""
        cust = (customer or "").strip()
        if cust.lower() == "all":
            cust = None
        prod = (product or "").strip()
        if prod.lower() == "all":
            prod = None

        directory = self._directory_distributors(allowed_companies=allowed_companies)
        if distributor_id:
            directory = [d for d in directory if d.id == int(distributor_id)]

        filter_kw = dict(
            segment=seg,
            location=loc,
            customer=cust,
            product=prod,
            distributor_id=distributor_id,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

        agg_q = (
            select(
                SalesRecord.distributor_id.label("distributor_id"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
                func.count(func.distinct(SalesRecord.customer_name)).label("customers"),
                func.count(func.distinct(SalesRecord.product)).label("products"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                Distributor.is_deleted.is_(False),
                SalesRecord.distributor_id.is_not(None),
            )
            .group_by(SalesRecord.distributor_id)
        )
        agg_q = self.sales._apply_filters(agg_q, **filter_kw)
        if month_keys is not None:
            if not month_keys:
                agg_q = agg_q.where(SalesRecord.id == -1)
            else:
                agg_q = agg_q.where(reporting_month_expr().in_(month_keys))

        stats_by_id: Dict[int, Dict[str, Any]] = {}
        for row in self.db.execute(agg_q).all():
            did = int(row.distributor_id)
            stats_by_id[did] = {
                "qty": _to_float(row.qty),
                "customers": int(row.customers or 0),
                "products": int(row.products or 0),
            }

        # Dominant location per distributor (period-scoped)
        loc_q = (
            select(
                SalesRecord.distributor_id.label("distributor_id"),
                SalesRecord.location.label("location"),
                func.sum(SalesRecord.quantity).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                Distributor.is_deleted.is_(False),
                SalesRecord.distributor_id.is_not(None),
                SalesRecord.location.is_not(None),
                SalesRecord.location != "",
            )
            .group_by(SalesRecord.distributor_id, SalesRecord.location)
        )
        loc_q = self.sales._apply_filters(loc_q, **filter_kw)
        if month_keys is not None:
            if not month_keys:
                loc_q = loc_q.where(SalesRecord.id == -1)
            else:
                loc_q = loc_q.where(reporting_month_expr().in_(month_keys))

        best_location: Dict[int, tuple[str, float]] = {}
        for row in self.db.execute(loc_q).all():
            did = int(row.distributor_id)
            name = str(row.location or "").strip()
            qty = _to_float(row.qty)
            if not name:
                continue
            prev = best_location.get(did)
            if prev is None or qty > prev[1]:
                best_location[did] = (name, qty)

        # Customer contribution for distributors that have sales
        cust_q = (
            select(
                SalesRecord.distributor_id.label("distributor_id"),
                SalesRecord.customer_name.label("customer"),
                func.count(func.distinct(SalesRecord.product)).label("product_count"),
                func.coalesce(func.sum(SalesRecord.quantity), 0).label("qty"),
            )
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .join(Distributor, Distributor.id == SalesRecord.distributor_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                Distributor.is_deleted.is_(False),
                SalesRecord.distributor_id.is_not(None),
                SalesRecord.customer_name.is_not(None),
                SalesRecord.customer_name != "",
            )
            .group_by(SalesRecord.distributor_id, SalesRecord.customer_name)
            .order_by(
                SalesRecord.distributor_id.asc(),
                func.sum(SalesRecord.quantity).desc(),
            )
        )
        cust_q = self.sales._apply_filters(cust_q, **filter_kw)
        if month_keys is not None:
            if not month_keys:
                cust_q = cust_q.where(SalesRecord.id == -1)
            else:
                cust_q = cust_q.where(reporting_month_expr().in_(month_keys))

        customers_by_id: Dict[int, List[Dict[str, Any]]] = {}
        for row in self.db.execute(cust_q).all():
            did = int(row.distributor_id)
            qty = round(_to_float(row.qty), 3)
            customers_by_id.setdefault(did, []).append(
                {
                    "customer": str(row.customer or ""),
                    "product_count": int(row.product_count or 0),
                    "sales_mt": qty,
                    "sales_mt_display": format_quantity(qty),
                }
            )

        ranking: List[Dict[str, Any]] = []
        for d in directory:
            stats = stats_by_id.get(d.id) or {
                "qty": 0.0,
                "customers": 0,
                "products": 0,
            }
            qty = round(float(stats["qty"]), 3)
            stored = normalize_location(d.region)
            sales_loc = best_location.get(d.id, ("", 0.0))[0]
            place = stored or normalize_location(sales_loc)
            if loc and place.casefold() != loc.casefold():
                continue
            if country_key and country_group(place) != country_key:
                continue
            loc_label = place or "—"
            name = ((d.company or "").strip() or (d.name or "").strip() or f"Distributor #{d.id}")
            ranking.append(
                {
                    "distributor_id": d.id,
                    "distributor": name,
                    "location": loc_label,
                    "country": country_label(place) or "—",
                    "customers": int(stats["customers"]),
                    "products": int(stats["products"]),
                    "sales_mt": qty,
                    "sales_mt_display": format_quantity(qty),
                    "has_sales": qty > 0,
                    "customer_contribution": customers_by_id.get(d.id, []),
                }
            )

        ranking.sort(key=lambda r: (-r["sales_mt"], r["distributor"].casefold()))
        for i, row in enumerate(ranking, start=1):
            row["rank"] = i

        total = len(ranking)
        submitted = sum(1 for r in ranking if r["has_sales"])
        top = ranking[0] if ranking and ranking[0]["has_sales"] else None
        runner = ranking[1] if len(ranking) > 1 and ranking[1]["has_sales"] else None

        return {
            "kpis": {
                "top_performer": {
                    "distributor": top["distributor"] if top else "—",
                    "distributor_id": top["distributor_id"] if top else None,
                    "sales_mt": top["sales_mt"] if top else 0.0,
                    "sales_mt_display": top["sales_mt_display"] if top else format_quantity(0),
                },
                "runner_up": {
                    "distributor": runner["distributor"] if runner else "—",
                    "distributor_id": runner["distributor_id"] if runner else None,
                    "sales_mt": runner["sales_mt"] if runner else 0.0,
                    "sales_mt_display": runner["sales_mt_display"] if runner else format_quantity(0),
                },
                "active_distributors": {
                    "submitted": submitted,
                    "total": total,
                    "label": f"{submitted} / {total} Distributors",
                },
            },
            "ranking": ranking,
            "filters": {
                "fiscal_year_start": fiscal_year_start,
                "period": period,
                "segment": segment or "All",
                "location": location or "All",
                "country": country or "All",
                "distributor_id": distributor_id,
                "customer": customer or "All",
                "product": product or "All",
                "start_month": start_month,
                "end_month": end_month,
            },
        }
