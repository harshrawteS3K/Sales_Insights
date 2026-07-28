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


class DashboardService:
    """Aggregations for dashboard and visualizations pages."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sales = SalesRecordRepository(db)
        self.distributors = DistributorRepository(db)
        self.reports = ReportRepository(db)
        self.emails = EmailMessageRepository(db)
        self.sync_jobs = SyncJobRepository(db)

    def summary(self) -> DashboardSummary:
        """Build high-level dashboard summary."""
        total_qty = float(self.sales.total_quantity())
        total_distributors = self.distributors.count()
        total_reports = self.reports.count()
        total_sales = self.sales.count()
        total_emails = self.emails.count()
        pending = self.reports.count_by_status(ReportStatus.PENDING.value)
        failed = self.reports.count_by_status(ReportStatus.FAILED.value)
        latest_sync = self.sync_jobs.get_latest()
        last_sync_at = (
            format_audit_timestamp(latest_sync.completed_at or latest_sync.started_at)
            if latest_sync
            else None
        )
        product_qtys = self.sales.product_quantities()
        top_product = product_qtys[0]["product"] if product_qtys else "-"

        kpis = [
            KpiItem(label="TOTAL DISTRIBUTORS", value=str(total_distributors)),
            KpiItem(label="TOTAL QTY (KG)", value=format_quantity(total_qty)),
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

    def product_quantities(self, *, period: Optional[str] = None) -> List[ProductQty]:
        """GET /api/visualizations/products."""
        rows = self.sales.product_quantities(period=period)
        return [ProductQty(**row) for row in rows]

    def distributor_totals(self, *, period: Optional[str] = None) -> List[DistributorTotal]:
        """GET /api/visualizations/distributors."""
        rows = self.sales.distributor_totals(period=period)
        return [DistributorTotal(**row) for row in rows]

    def product_mix(self, *, period: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Pie/mix data for products (frontend Visualizations contract).

        Returns Top 7 products by quantity as percentage share, plus an
        aggregated "Others" slice. Shape: {name, value, color}.
        """
        rows = self.sales.product_quantities(period=period)
        if not rows:
            return []

        sorted_rows = sorted(rows, key=lambda r: float(r["qty"]), reverse=True)
        total_qty = sum(float(r["qty"]) for r in sorted_rows)
        if total_qty <= 0:
            return []

        top7 = sorted_rows[:7]
        others_qty = sum(float(r["qty"]) for r in sorted_rows[7:])

        result: List[Dict[str, Any]] = [
            {
                "name": str(row["product"]),
                "value": round((float(row["qty"]) / total_qty) * 100),
                "color": PRODUCT_MIX_COLORS[i % len(PRODUCT_MIX_COLORS)],
            }
            for i, row in enumerate(top7)
        ]
        if others_qty > 0 or len(sorted_rows) > 7:
            result.append(
                {
                    "name": "Others",
                    "value": round((others_qty / total_qty) * 100),
                    "color": PRODUCT_MIX_OTHERS_COLOR,
                }
            )
        return result

    def product_bar(self, *, period: Optional[str] = None) -> List[Dict[str, Any]]:
        """Bar chart data for products."""
        return self.sales.product_quantities(period=period)

    def dist_product_mix(
        self,
        *,
        period: Optional[str] = None,
        products: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Distributor × product pivot."""
        focus = products or ["CB 300", "CB 4600", "CB 4400", "CB 548"]
        return self.sales.distributor_product_mix(focus, period=period)

    def top_distributors(self, *, period: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Top N distributors by quantity."""
        rows = self.sales.distributor_totals(period=period)
        return [
            {"name": row["name"], "qty": row["qty"]}
            for row in rows[:limit]
        ]

    def products_kpi(self) -> List[KpiItem]:
        """Products tab KPIs."""
        products = self.sales.distinct_products()
        total_qty = float(self.sales.total_quantity())
        product_qtys = self.sales.product_quantities()
        top_product = product_qtys[0]["product"] if product_qtys else "-"
        distributors = self.distributors.count()
        reports = self.reports.count()
        return [
            KpiItem(label="TOTAL PRODUCTS", value=str(len(products))),
            KpiItem(label="TOTAL QTY (KG)", value=format_quantity(total_qty)),
            KpiItem(label="TOP PRODUCT", value=str(top_product)),
            KpiItem(
                label="REPORTED THIS PERIOD",
                value=f"{reports} / {max(distributors, reports)}",
            ),
        ]

    def distributors_kpi(self) -> List[KpiItem]:
        """Distributors tab KPIs (five cards for Visualizations UI)."""
        totals = self.sales.distributor_totals()
        total_qty = sum(float(item["qty"]) for item in totals)
        count = len(totals)
        top = totals[0]["name"] if totals else "-"
        avg_qty = total_qty / count if count else 0.0
        distributors = self.distributors.count()
        reports = self.reports.count()
        return [
            KpiItem(label="TOTAL DISTRIBUTORS", value=str(count)),
            KpiItem(label="TOTAL QTY (KG)", value=format_quantity(total_qty)),
            KpiItem(label="AVG QTY / DIST.", value=format_quantity(avg_qty)),
            KpiItem(label="TOP DISTRIBUTOR", value=str(top)),
            KpiItem(
                label="REPORTED THIS PERIOD",
                value=f"{reports} / {max(distributors, reports)}",
            ),
        ]

    def product_filter_options(self) -> FilterOptions:
        """Filter options for products visualizations."""
        products = self.sales.distinct_products()
        periods = self.sales.distinct_periods()
        return FilterOptions(
            product=["All", *products],
            period=["All", *periods],
        )

    def distributor_filter_options(self) -> FilterOptions:
        """Filter options for distributor visualizations."""
        distributors = [d.name for d in self.distributors.list(limit=1000)]
        periods = self.sales.distinct_periods()
        return FilterOptions(
            distributor=["All", *distributors],
            period=["All", *periods],
        )
