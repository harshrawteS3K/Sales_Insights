"""Business Aggregation Engine — dynamic period rollups over ACTIVE quarterly data.

No quarterly tables. No duplicate storage. SQL aggregation only.
Designed for Quarterly today; Yearly / Half-Yearly / FY / custom via PeriodSpec.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.exceptions import ValidationAppError
from app.repositories.sales_record_repository import SalesRecordRepository
from app.utils.period_calendar import (
    available_quarter_labels,
    resolve_period,
)
from app.utils.quantity import format_quantity

logger = get_logger(__name__)

# Display unit for all business reporting (values stored as Excel quantities; label = MT)
QUANTITY_UNIT = "MT"


class BusinessAggregationService:
    """Reusable engine for company-centric period aggregations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sales = SalesRecordRepository(db)

    def available_quarters(self) -> List[str]:
        """Quarter labels derived from ACTIVE reporting months."""
        months = self.sales.distinct_column_values("period")
        return available_quarter_labels(months)

    def available_companies(self) -> List[str]:
        """Distributor Company names with ACTIVE sales."""
        return self.sales.distinct_distributors_with_sales()

    def quarterly_summary(
        self,
        *,
        quarter_label: Optional[str] = None,
        quarter: Optional[int] = None,
        year: Optional[int] = None,
        company: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Case 1 — All companies (or filtered): one summary row per company.

        Case 2 — When ``company`` is set: still returns summary list (0–1 rows)
        plus callers may request ``quarterly_report`` for customer-wise detail.
        """
        try:
            spec = resolve_period(
                quarter_label=quarter_label,
                quarter=quarter,
                year=year,
            )
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc

        rows = self.sales.quarterly_company_summary(
            spec.month_list,
            company=company,
        )
        data = [
            {
                "company": r["company"],
                "quarter": spec.label,
                "totalQuantity": r["qty"],
                "totalQuantityDisplay": format_quantity(r["qty"]),
                "unit": QUANTITY_UNIT,
                "productsSold": r["products"],
                "customerCount": r["customers"],
                "reportsIncluded": r["reports"],
                "monthsSubmitted": r["months"],
                "monthsExpected": spec.month_list,
                "isPartial": len(r["months"]) < len(spec.month_list),
            }
            for r in rows
        ]
        logger.debug(
            "Quarterly summary | period={} | companies={} | company_filter={!r}",
            spec.label,
            len(data),
            company,
        )
        return {
            "period": {
                "label": spec.label,
                "kind": spec.kind,
                "year": spec.year,
                "months": spec.month_list,
            },
            "unit": QUANTITY_UNIT,
            "totalCompanies": len(data),
            "grandTotalQuantity": sum(d["totalQuantity"] for d in data),
            "data": data,
        }

    def quarterly_report(
        self,
        *,
        company: str,
        quarter_label: Optional[str] = None,
        quarter: Optional[int] = None,
        year: Optional[int] = None,
        page: int = 1,
        page_size: int = 10,
        search: Optional[str] = None,
        sort_by: str = "quantity",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """
        Case 2 — Virtual Quarterly Report for one Distributor Company.

        Header KPIs from company summary; detail grid is Customer × Segment × Product
        with server-side pagination, search, and sorting over ACTIVE quarterly data.
        """
        if not company or not company.strip():
            raise ValidationAppError("Distributor Company is required for quarterly report")

        try:
            spec = resolve_period(
                quarter_label=quarter_label,
                quarter=quarter,
                year=year,
            )
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc

        company_name = company.strip()
        empty_page = {
            "items": [],
            "totalRecords": 0,
            "totalPages": 0,
            "currentPage": max(1, int(page or 1)),
            "pageSize": max(1, min(int(page_size or 10), 100)),
        }
        period_block = {
            "label": spec.label,
            "kind": spec.kind,
            "year": spec.year,
            "months": spec.month_list,
        }

        summary_rows = self.sales.quarterly_company_summary(
            spec.month_list,
            company=company_name,
        )
        if not summary_rows:
            return {
                "period": period_block,
                "company": company_name,
                "unit": QUANTITY_UNIT,
                "totalQuantity": 0.0,
                "totalQuantityDisplay": "0",
                "productsSold": 0,
                "customerCount": 0,
                "reportsIncluded": 0,
                "monthsSubmitted": [],
                "monthsExpected": spec.month_list,
                "isPartial": True,
                "products": [],
                **empty_page,
            }

        header = summary_rows[0]
        detail = self.sales.quarterly_customer_detail(
            spec.month_list,
            company=company_name,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        items = [
            {
                "srNo": row["srNo"],
                "customer": row["customer"],
                "segment": row["segment"],
                "product": row["product"],
                "quantity": row["quantity"],
                "quantityDisplay": format_quantity(row["quantity"]),
                "unit": QUANTITY_UNIT,
                "contributionPct": row["contributionPct"],
            }
            for row in detail["items"]
        ]
        return {
            "period": period_block,
            "company": header["company"],
            "unit": QUANTITY_UNIT,
            "totalQuantity": header["qty"],
            "totalQuantityDisplay": format_quantity(header["qty"]),
            "productsSold": header["products"],
            "customerCount": header["customers"],
            "reportsIncluded": header["reports"],
            "monthsSubmitted": header["months"],
            "monthsExpected": spec.month_list,
            "isPartial": len(header["months"]) < len(spec.month_list),
            "items": items,
            "totalRecords": detail["totalRecords"],
            "totalPages": detail["totalPages"],
            "currentPage": detail["currentPage"],
            "pageSize": detail["pageSize"],
            "products": [],
        }
