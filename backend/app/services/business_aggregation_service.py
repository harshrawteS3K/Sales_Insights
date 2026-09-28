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
from app.utils.quantity import format_mt, kg_to_mt_display

logger = get_logger(__name__)

# Display unit. Stored sales quantities remain kilograms.
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
        kg_total = 0.0
        data = []
        for row in rows:
            kg_total += float(row["qty"] or 0)
            quantity = kg_to_mt_display(row["qty"])
            data.append(
                {
                    "company": row["company"],
                    "quarter": spec.label,
                    "totalQuantity": quantity,
                    "quantity": quantity,
                    "totalQuantityDisplay": format_mt(quantity),
                    "unit": QUANTITY_UNIT,
                    "productsSold": row["products"],
                    "customerCount": row["customers"],
                    "reportsIncluded": row["reports"],
                    "monthsSubmitted": row["months"],
                    "monthsExpected": spec.month_list,
                    "isPartial": len(row["months"]) < len(spec.month_list),
                }
            )
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
            "grandTotalQuantity": kg_to_mt_display(kg_total),
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
                "totalQuantityDisplay": format_mt(0),
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
        items = []
        for row in detail["items"]:
            quantity = kg_to_mt_display(row["quantity"])
            items.append(
                {
                    "srNo": row["srNo"],
                    "customer": row["customer"],
                    "segment": row["segment"],
                    "product": row["product"],
                    "quantity": quantity,
                    "quantityDisplay": format_mt(quantity),
                    "unit": QUANTITY_UNIT,
                    "contributionPct": row["contributionPct"],
                }
            )
        header_qty = kg_to_mt_display(header["qty"])
        return {
            "period": period_block,
            "company": header["company"],
            "unit": QUANTITY_UNIT,
            "totalQuantity": header_qty,
            "quantity": header_qty,
            "totalQuantityDisplay": format_mt(header_qty),
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
