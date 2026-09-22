"""Sales Insights analytics API for Visualizations & Analytics."""

from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.rbac import (
    RequireUser,
    distributor_companies_scope_for_user,
    segment_scope_for_user,
)
from app.schemas.common import DataResponse
from app.services.sales_insights_service import SalesInsightsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _service(db: Session = Depends(get_db)) -> SalesInsightsService:
    return SalesInsightsService(db)


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() == "all":
        return None
    return text


@router.get("/filter-options", summary="Sales Insights filter dropdowns")
def get_filter_options(
    current: RequireUser,
    db: Session = Depends(get_db),
    service: SalesInsightsService = Depends(_service),
) -> DataResponse[dict]:
    allowed = segment_scope_for_user(current, db)
    companies = distributor_companies_scope_for_user(current, db)
    data = service.filter_options(
        allowed_segments=allowed,
        allowed_companies=companies,
    )
    return DataResponse(data=data)


@router.get("/sales-insights", summary="Sales Insights analytics payload")
def get_sales_insights(
    current: RequireUser,
    db: Session = Depends(get_db),
    service: SalesInsightsService = Depends(_service),
    distributor_id: Optional[int] = Query(None),
    customer: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    segment: Optional[str] = Query(None),
    fiscal_year_start: Optional[int] = Query(
        None, description="Indian FY start year e.g. 2025 for FY 2025–26"
    ),
    period: Optional[str] = Query(
        "full_year",
        description="full_year | q1 | q2 | q3 | q4 | last_3_months | last_6_months | custom",
    ),
    start_month: Optional[str] = Query(None, description="YYYY-MM for custom range"),
    end_month: Optional[str] = Query(None, description="YYYY-MM for custom range"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> DataResponse[dict]:
    allowed = segment_scope_for_user(current, db)
    companies = distributor_companies_scope_for_user(current, db)
    data = service.sales_insights(
        distributor_id=distributor_id,
        customer=_clean(customer),
        product=_clean(product),
        location=_clean(location),
        segment=_clean(segment),
        fiscal_year_start=fiscal_year_start,
        period=period,
        start_month=start_month,
        end_month=end_month,
        search=search,
        page=page,
        page_size=page_size,
        allowed_segments=allowed,
        allowed_companies=companies,
    )
    return DataResponse(data=data)


@router.get("/sales-insights/export", summary="Export Sales Insights table to Excel")
def export_sales_insights(
    current: RequireUser,
    db: Session = Depends(get_db),
    service: SalesInsightsService = Depends(_service),
    distributor_id: Optional[int] = Query(None),
    customer: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    segment: Optional[str] = Query(None),
    fiscal_year_start: Optional[int] = Query(None),
    period: Optional[str] = Query("full_year"),
    start_month: Optional[str] = Query(None),
    end_month: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> StreamingResponse:
    allowed = segment_scope_for_user(current, db)
    companies = distributor_companies_scope_for_user(current, db)
    rows = service.export_rows(
        distributor_id=distributor_id,
        customer=_clean(customer),
        product=_clean(product),
        location=_clean(location),
        segment=_clean(segment),
        fiscal_year_start=fiscal_year_start,
        period=period,
        start_month=start_month,
        end_month=end_month,
        search=search,
        allowed_segments=allowed,
        allowed_companies=companies,
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Insights"
    headers = [
        "Customer Name",
        "Product",
        "Location",
        "Month",
        "Sales Quantity (MT)",
        "Distributor",
    ]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sales_insights.xlsx"'},
    )
