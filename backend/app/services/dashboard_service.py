"""Dashboard and visualization aggregation service."""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.constants import PRODUCT_MIX_COLORS, PRODUCT_MIX_OTHERS_COLOR
from app.core.logging import get_logger
from app.enums import ReportStatus
from app.repositories.distributor_repository import DistributorRepository
from app.repositories.email_repository import EmailMessageRepository
from app.repositories.master_repository import SyncJobRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.sales_record_repository import SalesRecordRepository
from app.schemas.dashboard import (
    DashboardSummary,
    DistributorTotal,
    FilterOptions,
    KpiItem,
    ProductQty,
)
from app.utils.datetime_utils import format_audit_timestamp
from app.utils.quantity import format_quantity

logger = get_logger(__name__)


def _norm_filter(value: Optional[str]) -> Optional[str]:
    if not value or str(value).strip().lower() in ("", "all"):
        return None
    return str(value).strip()


class DashboardService:
    """Aggregations for dashboard and visualizations pages."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sales = SalesRecordRepository(db)
        self.distributors = DistributorRepository(db)
        self.reports = ReportRepository(db)
        self.emails = EmailMessageRepository(db)
        self.sync_jobs = SyncJobRepository(db)

    def summary(
        self,
        *,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> DashboardSummary:
        """Build high-level dashboard summary."""
        total_qty = float(
            self.sales.total_quantity(
                allowed_segments=allowed_segments,
                allowed_companies=allowed_companies,
            )
        )
        # Distributors that actually contribute active sales (matches Consolidated / charts)
        total_distributors = len(
            self.sales.distributor_totals(
                allowed_segments=allowed_segments,
                allowed_companies=allowed_companies,
            )
        )
        total_reports = self.sales.count_contributing_reports()
        total_sales = self.sales.count_active_with_parents()
        total_emails = self.emails.count()
        pending = self.reports.count_by_status(ReportStatus.PENDING.value)
        failed = self.reports.count_by_status(ReportStatus.FAILED.value)
        latest_sync = self.sync_jobs.get_latest()
        last_sync_at = (
            format_audit_timestamp(latest_sync.completed_at or latest_sync.started_at)
            if latest_sync
            else None
        )
        product_qtys = self.sales.product_quantities(
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        top_product = product_qtys[0]["product"] if product_qtys else "-"

        kpis = [
            KpiItem(label="TOTAL DISTRIBUTOR COMPANIES", value=str(total_distributors)),
            KpiItem(label="TOTAL QTY (MT)", value=format_quantity(total_qty)),
            KpiItem(label="TOTAL REPORTS", value=str(total_reports)),
            KpiItem(label="TOP PRODUCT", value=str(top_product)),
        ]
        logger.debug("Dashboard summary computed")
        return DashboardSummary(
            total_distributors=total_distributors,
            total_reports=total_reports,
            total_sales_records=total_sales,
            total_quantity=total_qty,
            total_emails_processed=total_emails,
            pending_reports=pending,
            failed_reports=failed,
            last_sync_at=last_sync_at,
            kpis=kpis,
        )

    def product_quantities(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[ProductQty]:
        """GET /api/visualizations/products."""
        rows = self.sales.product_quantities(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        return [ProductQty(**row) for row in rows]

    def distributor_totals(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[DistributorTotal]:
        """GET /api/visualizations/distributors."""
        rows = self.sales.distributor_totals(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        return [DistributorTotal(**row) for row in rows]

    def product_mix(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        top_n: int = 7,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Mix data for products (donut / treemap).

        Top N by quantity as percentage share + aggregated "Others".
        """
        rows = self.sales.product_quantities(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        if not rows:
            return []

        sorted_rows = sorted(rows, key=lambda r: float(r["qty"]), reverse=True)
        total_qty = sum(float(r["qty"]) for r in sorted_rows)
        if total_qty <= 0:
            return []

        n = max(1, min(int(top_n or 7), 50))
        top = sorted_rows[:n]
        others_qty = sum(float(r["qty"]) for r in sorted_rows[n:])

        result: List[Dict[str, Any]] = [
            {
                "name": str(row["product"]),
                "value": round((float(row["qty"]) / total_qty) * 100, 2),
                "qty": float(row["qty"]),
                "color": PRODUCT_MIX_COLORS[i % len(PRODUCT_MIX_COLORS)],
            }
            for i, row in enumerate(top)
        ]
        if others_qty > 0 or len(sorted_rows) > n:
            result.append(
                {
                    "name": "Others",
                    "value": round((others_qty / total_qty) * 100, 2),
                    "qty": others_qty,
                    "color": PRODUCT_MIX_OTHERS_COLOR,
                }
            )
        return result

    def product_bar(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        top_n: int = 10,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Top N products by quantity with remaining aggregated as Others."""
        rows = self.sales.product_quantities(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        if not rows:
            return []
        n = max(1, min(int(top_n or 10), 50))
        top = rows[:n]
        others_qty = sum(float(r["qty"]) for r in rows[n:])
        result = [{"product": r["product"], "qty": float(r["qty"])} for r in top]
        if others_qty > 0:
            result.append({"product": "Others", "qty": others_qty})
        return result

    def dist_product_mix(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        products: Optional[List[str]] = None,
        top_products: int = 4,
        distributor_limit: int = 15,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Distributor × product pivot — Top products × Top companies (scale-safe)."""
        p = _norm_filter(period)
        prod = _norm_filter(product)
        dist = _norm_filter(distributor)
        if products:
            focus = list(products)[: max(1, min(int(top_products or 4), 12))]
        else:
            ranked = self.sales.product_quantities(period=p, product=prod, distributor=dist, allowed_segments=allowed_segments, allowed_companies=allowed_companies)
            n = max(1, min(int(top_products or 4), 12))
            focus = [r["product"] for r in ranked[:n]]
        if not focus:
            return []
        return self.sales.distributor_product_mix(
            focus,
            period=p,
            product=prod,
            distributor=dist,
            distributor_limit=max(1, min(int(distributor_limit or 15), 50)),
        )

    def top_distributors(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        limit: int = 10,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Top N distributor companies by quantity (+ Others for remainder)."""
        rows = self.sales.distributor_totals(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        n = max(1, min(int(limit or 10), 50))
        top = rows[:n]
        others_qty = sum(float(r["qty"]) for r in rows[n:])
        result = [{"name": row["name"], "qty": row["qty"]} for row in top]
        if others_qty > 0:
            result.append({"name": "Others", "qty": others_qty})
        return result

    def distributor_contribution(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        top_n: int = 8,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Donut: distributor share of total quantity (Top N + Others)."""
        rows = self.sales.distributor_totals(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        if not rows:
            return []
        total = sum(float(r["qty"]) for r in rows)
        if total <= 0:
            return []
        n = max(1, min(int(top_n or 8), 30))
        top = rows[:n]
        others = sum(float(r["qty"]) for r in rows[n:])
        result = [
            {
                "name": r["name"],
                "value": round((float(r["qty"]) / total) * 100, 2),
                "qty": float(r["qty"]),
                "color": PRODUCT_MIX_COLORS[i % len(PRODUCT_MIX_COLORS)],
            }
            for i, r in enumerate(top)
        ]
        if others > 0:
            result.append(
                {
                    "name": "Others",
                    "value": round((others / total) * 100, 2),
                    "qty": others,
                    "color": PRODUCT_MIX_OTHERS_COLOR,
                }
            )
        return result

    def monthly_sales_trend(
        self,
        *,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Line chart: month → total quantity."""
        return self.sales.monthly_sales_trend(
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

    def distributor_month_heatmap(
        self,
        *,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        distributor_limit: int = 15,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Heatmap: distributor × month → quantity."""
        return self.sales.distributor_month_matrix(
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            distributor_limit=distributor_limit,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )

    def products_kpi(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[KpiItem]:
        """Products tab KPIs (ACTIVE data; respects filters)."""
        product_qtys = self.sales.product_quantities(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        total_qty = sum(float(r["qty"]) for r in product_qtys)
        top_product = product_qtys[0]["product"] if product_qtys else "-"
        dist_count = len(
            self.sales.distributor_totals(
                period=_norm_filter(period),
                product=_norm_filter(product),
                distributor=_norm_filter(distributor),
                allowed_segments=allowed_segments,
                allowed_companies=allowed_companies,
            )
        )
        return [
            KpiItem(label="TOTAL PRODUCTS", value=str(len(product_qtys))),
            KpiItem(label="TOTAL QTY (MT)", value=format_quantity(total_qty)),
            KpiItem(label="TOP PRODUCT", value=str(top_product)),
            KpiItem(label="DISTRIBUTORS", value=str(dist_count)),
        ]

    def distributors_kpi(
        self,
        *,
        period: Optional[str] = None,
        product: Optional[str] = None,
        distributor: Optional[str] = None,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
    ) -> List[KpiItem]:
        """Distributors tab KPIs (ACTIVE data; respects filters)."""
        totals = self.sales.distributor_totals(
            period=_norm_filter(period),
            product=_norm_filter(product),
            distributor=_norm_filter(distributor),
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
        total_qty = sum(float(item["qty"]) for item in totals)
        count = len(totals)
        top = totals[0]["name"] if totals else "-"
        avg_qty = total_qty / count if count else 0.0
        return [
            KpiItem(label="TOTAL DISTRIBUTOR COMPANIES", value=str(count)),
            KpiItem(label="TOTAL QTY (MT)", value=format_quantity(total_qty)),
            KpiItem(label="AVG QTY / COMPANY", value=format_quantity(avg_qty)),
            KpiItem(label="TOP DISTRIBUTOR COMPANY", value=str(top)),
            KpiItem(
                label="PRODUCTS",
                value=str(
                    len(
                        self.sales.product_quantities(
                            period=_norm_filter(period),
                            product=_norm_filter(product),
                            distributor=_norm_filter(distributor),
                            allowed_segments=allowed_segments,
                            allowed_companies=allowed_companies,
                        )
                    )
                ),
            ),
        ]

    def product_filter_options(self) -> FilterOptions:
        """Filter options for products visualizations (ACTIVE sales only)."""
        products = self.sales.distinct_products()
        periods = self.sales.distinct_periods()
        distributors = self.sales.distinct_distributors_with_sales()
        return FilterOptions(
            product=["All", *products],
            period=["All", *periods],
            distributor=["All", *distributors],
        )

    def distributor_filter_options(self) -> FilterOptions:
        """Filter options for distributor visualizations (ACTIVE sales names)."""
        distributors = self.sales.distinct_distributors_with_sales()
        periods = self.sales.distinct_periods()
        products = self.sales.distinct_products()
        return FilterOptions(
            distributor=["All", *distributors],
            period=["All", *periods],
            product=["All", *products],
        )
