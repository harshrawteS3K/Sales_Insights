"""One filter and one quantity total for every analytics visualization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import false, func, or_

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.distributor import Distributor
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.repositories.sales_record_repository import company_expr
from app.utils.quantity import round_mt

logger = get_logger(__name__)

_TOLERANCE_MT = 0.001


@dataclass
class AnalyticsFilter:
    """Shared filter passed into every analytics query."""

    financial_year: Optional[int] = None
    period: Optional[str] = None
    distributor_id: Optional[int] = None
    distributor: Optional[str] = None
    customer: Optional[str] = None
    product: Optional[str] = None
    location: Optional[str] = None
    segment: Optional[str] = None
    start_month: Optional[str] = None
    end_month: Optional[str] = None

    def month_window(self):
        from app.services.sales_insights_service import _period_year_months

        return _period_year_months(
            self.period,
            fiscal_year_start=self.financial_year,
            start_month=self.start_month,
            end_month=self.end_month,
        )

    def match_keys(self) -> Optional[List[str]]:
        from app.services.sales_insights_service import resolve_period_month_keys

        return resolve_period_month_keys(
            self.period,
            fiscal_year_start=self.financial_year,
            start_month=self.start_month,
            end_month=self.end_month,
        )

    def restrict(self, query):
        """Apply this filter. Period matches the row, the source month, or the report."""
        if self.distributor_id or self.distributor:
            clauses = []
            if self.distributor_id:
                clauses.append(SalesRecord.distributor_id == int(self.distributor_id))
            name = (self.distributor or "").strip().lower()
            if name and name != "all":
                clauses.append(func.lower(company_expr()) == name)
                clauses.append(func.lower(func.coalesce(Distributor.company, "")) == name)
                clauses.append(func.lower(func.coalesce(Distributor.name, "")) == name)
            query = query.where(or_(*clauses))
        keys = self.match_keys()
        if keys is None:
            return query
        if not keys:
            return query.where(false())
        return query.where(
            or_(
                func.trim(func.coalesce(SalesRecord.period, "")).in_(keys),
                func.trim(func.coalesce(SalesRecord.source_month, "")).in_(keys),
                func.trim(func.coalesce(Report.reporting_month, "")).in_(keys),
            )
        )


def align_quantities(amounts_kg: Sequence[float], *, total_kg: float) -> List[float]:
    """Align already-MT buckets so parts sum to the MT total (param names are legacy)."""
    target = round_mt(total_kg)
    converted = [round_mt(amount) for amount in amounts_kg]
    if not converted:
        return []
    drift = round(target - sum(converted), 3)
    if abs(drift) >= 0.0005:
        index = max(range(len(converted)), key=lambda i: converted[i])
        converted[index] = round(converted[index] + drift, 3)
    return converted


def log_integrity(
    *,
    kpi: float,
    monthly: Sequence[Dict[str, Any]],
    products: Sequence[Dict[str, Any]],
    customers: Sequence[Dict[str, Any]],
) -> None:
    """KPI, monthly trend, products, and customers must describe the same sales."""
    monthly_sum = round(sum(float(row.get("qty") or 0) for row in monthly), 3)
    product_sum = round(sum(float(row.get("qty") or 0) for row in products), 3)
    customer_sum = round(sum(float(row.get("qty") or 0) for row in customers), 3)
    kpi_mt = round(float(kpi or 0), 3)
    ok = (
        abs(kpi_mt - monthly_sum) <= _TOLERANCE_MT
        and abs(kpi_mt - product_sum) <= _TOLERANCE_MT
        and abs(kpi_mt - customer_sum) <= _TOLERANCE_MT
    )
    status = "PASS" if ok else "FAIL"
    message = (
        f"KPI Total = {kpi_mt:.3f}\n"
        f"Monthly Sum = {monthly_sum:.3f}\n"
        f"Product Sum = {product_sum:.3f}\n"
        f"Customer Sum = {customer_sum:.3f}\n"
        f"Status = {status}"
    )
    if get_settings().debug:
        logger.info(message)
    if not ok:
        logger.warning("Analytics integrity warning\n{}", message)
