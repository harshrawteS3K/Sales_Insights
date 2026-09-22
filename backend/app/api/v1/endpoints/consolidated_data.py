"""Consolidated Sales Data management endpoints."""

from datetime import date
from typing import Annotated, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.rbac import RequireAdmin, RequireUser, distributor_companies_scope_for_user, segment_scope_for_user
from app.dependencies.services import ConsolidatedDataServiceDep, DistributorServiceDep
from app.schemas.common import MessageResponse
from app.schemas.distributor import DistributorInfo
from app.schemas.sales_record import (
    ConsolidatedFilterOptions,
    ConsolidatedRecordsPage,
    DeleteReportPreview,
    DeleteReportRequest,
    DeleteResult,
    QuarterlyReportResponse,
    QuarterlySummaryResponse,
)
from app.services.business_aggregation_service import BusinessAggregationService

router = APIRouter(prefix="/consolidated-data", tags=["Consolidated Data"])


@router.get(
    "/filter-options",
    response_model=ConsolidatedFilterOptions,
    summary="Dynamic filter dropdown values (SELECT DISTINCT)",
)
def get_filter_options(
    service: ConsolidatedDataServiceDep,
    current: RequireUser,
    db: Annotated[Session, Depends(get_db)],
) -> ConsolidatedFilterOptions:
    """Return companies, customers, segments, products, periods, quarters from DB."""
    allowed = segment_scope_for_user(current, db)
    companies = distributor_companies_scope_for_user(current, db)
    return service.filter_options(allowed_segments=allowed, allowed_companies=companies)


@router.get(
    "/quarterly/summary",
    response_model=QuarterlySummaryResponse,
    summary="Quarterly business summary by Distributor Company",
)
def get_quarterly_summary(
    _: RequireUser,
    db: Annotated[Session, Depends(get_db)],
    quarter: Optional[str] = Query(None, description="FY quarter label e.g. FY 2025-26 • Q1"),
    company: Optional[str] = Query(
        None, description="Distributor Company (optional; All when omitted)"
    ),
) -> QuarterlySummaryResponse:
    """Virtual quarterly summary over ACTIVE quarterly reports (not persisted)."""
    engine = BusinessAggregationService(db)
    payload = engine.quarterly_summary(quarter_label=quarter, company=company)
    return QuarterlySummaryResponse(**payload)


@router.get(
    "/quarterly/report",
    response_model=QuarterlyReportResponse,
    summary="Virtual quarterly report for one Distributor Company",
)
def get_quarterly_report(
    current: RequireUser,
    db: Annotated[Session, Depends(get_db)],
    company: str = Query(..., min_length=1, description="Distributor Company"),
    quarter: Optional[str] = Query(None, description="FY quarter label e.g. FY 2025-26 • Q1"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(10, ge=1, le=100, description="Rows per page"),
    search: Optional[str] = Query(
        None, description="Case-insensitive match on customer, segment, or product"
    ),
    sort_by: str = Query(
        "quantity",
        description="customer | segment | product | quantity | contributionPct",
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> QuarterlyReportResponse:
    """Aggregate ACTIVE quarterly reports for company + quarter (SQL only)."""
    engine = BusinessAggregationService(db)
    payload = engine.quarterly_report(
        company=company,
        quarter_label=quarter,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    # Log once per report open (first page only) to avoid pagination noise
    if page == 1 and not search:
        from app.services.audit_service import AuditService
        from app.schemas.audit import AuditTrailCreate
        from app.enums import AuditAction

        AuditService(db).log(
            AuditTrailCreate(
                user_name=current.name,
                user_role=current.role.value if hasattr(current.role, "value") else str(current.role),
                action=AuditAction.GENERATED,
                details=(
                    f"Generated quarterly report for {company} · {quarter or payload.get('period', {}).get('label', '')} "
                    f"({payload.get('totalQuantityDisplay', 0)} MT)"
                ),
                entity_type="consolidated_data",
                module="Consolidated Data",
                status="Success",
                report_name=f"{company} {quarter or ''}".strip(),
                extra_metadata={
                    "company": company,
                    "quarter": quarter,
                    "totalQuantity": payload.get("totalQuantity"),
                },
            )
        )
    return QuarterlyReportResponse(**payload)


@router.get(
    "/records",
    response_model=ConsolidatedRecordsPage,
    summary="Consolidated sales records (server-side filter + pagination)",
)
def get_sales_records(
    service: ConsolidatedDataServiceDep,
    current: RequireUser,
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=5000),
    search: Optional[str] = Query(None, description="Case-insensitive partial match"),
    distributor: Optional[str] = Query(None),
    customer: Optional[str] = Query(None),
    segment: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    period: Optional[str] = Query(
        None, description="Reporting Quarter (legacy query name)"
    ),
    reporting_month: Optional[str] = Query(
        None, description="Reporting Quarter", alias="reportingMonth"
    ),
    reporting_quarter: Optional[str] = Query(
        None, description="Reporting Quarter", alias="reportingQuarter"
    ),
    quarter: Optional[str] = Query(
        None, description="FY quarter label e.g. FY 2025-26 • Q1",
    ),
    quantity_min: Optional[float] = Query(None),
    quantity_max: Optional[float] = Query(None),
    imported_from: Optional[date] = Query(None),
    imported_to: Optional[date] = Query(None),
    sort_by: str = Query("id"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    audit: bool = Query(False, description="Write audit log for this filter/search"),
    page_by: str = Query(
        "reports",
        alias="pageBy",
        pattern="^(reports|rows)$",
        description="Paginate by complete reports (default) or sales rows",
    ),
) -> ConsolidatedRecordsPage:
    """GET /api/consolidated-data/records — filtered, paginated, report-grouped."""
    allowed = segment_scope_for_user(current, db)
    companies = distributor_companies_scope_for_user(current, db)
    return service.list_records(
        skip=skip,
        limit=limit,
        search=search,
        distributor=distributor,
        customer=customer,
        segment=segment,
        location=location,
        product=product,
        company=company,
        period=period,
        reporting_month=reporting_quarter or reporting_month,
        quarter=quarter,
        quantity_min=quantity_min,
        quantity_max=quantity_max,
        imported_from=imported_from,
        imported_to=imported_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        actor=current.name,
        audit_search=audit,
        page_by=page_by,
        allowed_segments=allowed,
        allowed_companies=companies,
    )


@router.get(
    "/distributors",
    response_model=Dict[str, DistributorInfo],
    summary="Distributor details map",
)
def get_distributor_details(
    service: DistributorServiceDep,
    _: RequireUser,
) -> Dict[str, DistributorInfo]:
    """GET /api/consolidated-data/distributors — frontend distributor detail map."""
    return service.details_map()


@router.delete(
    "/all",
    response_model=DeleteResult,
    summary="Soft-delete all consolidated reports and sales (Admin)",
)
def wipe_all_consolidated(
    service: ConsolidatedDataServiceDep,
    current: RequireAdmin,
) -> DeleteResult:
    """DELETE /api/consolidated-data/all — clear Consolidated tab data."""
    return service.wipe_all_reports(actor=current.name)


@router.get(
    "/report/preview",
    response_model=DeleteReportPreview,
    summary="Preview rows that would be deleted for distributor + reporting quarter",
)
def preview_delete_report(
    service: ConsolidatedDataServiceDep,
    _: RequireAdmin,
    distributor: str = Query(...),
    reportingQuarter: Optional[str] = Query(None),
    reportingMonth: Optional[str] = Query(None),
    period: Optional[str] = Query(None, description="Legacy alias for reportingQuarter"),
) -> DeleteReportPreview:
    """Preview delete-report impact before confirmation."""
    month = (reportingQuarter or reportingMonth or period or "").strip()
    return service.preview_delete_report(distributor, month)


@router.delete(
    "/report",
    response_model=DeleteResult,
    summary="Delete imported report (distributor + reporting quarter)",
)
def delete_report(
    payload: DeleteReportRequest,
    service: ConsolidatedDataServiceDep,
    current: RequireAdmin,
) -> DeleteResult:
    """
    DELETE /api/consolidated-data/report

    Removes all sales rows for the given Distributor + Reporting Quarter.
    """
    return service.delete_report(
        payload.distributor, payload.resolved_month(), actor=current.name
    )


@router.post(
    "/export-audit",
    response_model=MessageResponse,
    summary="Audit log for consolidated data export",
)
def audit_export(
    service: ConsolidatedDataServiceDep,
    current: RequireUser,
    total: int = Query(0, ge=0),
    summary: str = Query(""),
) -> MessageResponse:
    """Record an export action in the audit trail."""
    service.log_export(actor=current.name, total=total, filters_summary=summary)
    return MessageResponse(message="Export audited")


@router.delete(
    "/{record_id}",
    response_model=DeleteResult,
    summary="Delete a single sales record",
)
def delete_record(
    record_id: int,
    service: ConsolidatedDataServiceDep,
    current: RequireAdmin,
) -> DeleteResult:
    """DELETE /api/consolidated-data/{recordId} — soft-delete one sales row."""
    return service.delete_record(record_id, actor=current.name)
