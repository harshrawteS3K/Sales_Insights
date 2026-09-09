"""Report endpoints (backend + frontend-aligned contracts)."""

from typing import List, Optional

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.dependencies.rbac import RequireAdmin, RequireUser
from app.dependencies.services import ReportServiceDep
from app.schemas.common import DataResponse, MessageResponse
from app.schemas.report import (
    FrontendReport,
    ReportCreate,
    ReportFilterCategories,
    ReportListResponse,
    ReportResponse,
    ReportUpdate,
    ReportUploadResponse,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("", response_model=List[FrontendReport], summary="List reports (frontend shape)")
def list_reports_frontend(
    service: ReportServiceDep,
    _: RequireUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=10000),
) -> List[FrontendReport]:
    """GET /api/reports — frontend ExistingReports contract."""
    reports = service.list_reports(skip=skip, limit=limit)
    return service.to_frontend_reports(reports)


@router.get(
    "/full",
    response_model=ReportListResponse,
    summary="List reports (full backend shape)",
)
def list_reports_full(
    service: ReportServiceDep,
    _: RequireUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=10000),
    status_filter: Optional[str] = Query(None, alias="status"),
    source: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
) -> ReportListResponse:
    """Full report list with filters."""
    reports = service.list_reports(
        skip=skip,
        limit=limit,
        status=status_filter,
        source=source,
        report_type=report_type,
    )
    return ReportListResponse(
        data=[ReportResponse.model_validate(r) for r in reports],
        total=service.count_reports(
            status=status_filter,
            source=source,
            report_type=report_type,
        ),
    )


@router.get(
    "/filter-categories",
    response_model=ReportFilterCategories,
    summary="Report filter categories",
)
def filter_categories(service: ReportServiceDep, _: RequireUser) -> ReportFilterCategories:
    """GET /api/reports/filter-categories."""
    return ReportFilterCategories(**service.filter_categories())


@router.get(
    "/suggested-questions",
    response_model=List[str],
    summary="Suggested chat questions",
)
def suggested_questions(service: ReportServiceDep, _: RequireUser) -> List[str]:
    """GET /api/reports/suggested-questions."""
    return service.suggested_questions()


@router.get("/{report_id}", response_model=DataResponse[ReportResponse], summary="Get report")
def get_report(
    report_id: int,
    service: ReportServiceDep,
    _: RequireUser,
) -> DataResponse[ReportResponse]:
    """Get report by id."""
    report = service.get_report(report_id)
    return DataResponse(data=ReportResponse.model_validate(report))


@router.post(
    "",
    response_model=DataResponse[ReportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create report metadata",
)
def create_report(
    payload: ReportCreate,
    service: ReportServiceDep,
    current: RequireAdmin,
) -> DataResponse[ReportResponse]:
    """Create report metadata (Admin)."""
    report = service.create_report(payload, actor=current.name)
    return DataResponse(data=ReportResponse.model_validate(report), message="Report created")


@router.post("/upload", response_model=ReportUploadResponse, summary="Upload and ingest sales Excel")
async def upload_report(
    service: ReportServiceDep,
    current: RequireAdmin,
    file: UploadFile = File(
        ...,
        description="multipart/form-data field 'file'; Excel only (.xlsx or .xlsm). .xls and .csv are rejected.",
    ),
    reporting_quarter: Optional[str] = Form(
        default=None,
        description="Reporting quarter e.g. Q3 2026 (required for ERP ingest; not read from Excel)",
    ),
    distributor_company: Optional[str] = Form(
        default=None,
        description="Distributor company (optional if resolvable later from sender)",
    ),
) -> ReportUploadResponse:
    """Upload a distributor ERP Excel via multipart field `file` (.xlsx/.xlsm only; Admin)."""
    report, inserted, duplicate, _quality = await service.upload_and_ingest(
        file,
        actor=current.name,
        uploaded_by=current.user_id,
        reporting_quarter=reporting_quarter,
        distributor_company=distributor_company,
    )
    return ReportUploadResponse(
        message="Report uploaded and processed" if not duplicate else "Duplicate report",
        report=ReportResponse.model_validate(report),
        records_inserted=inserted,
        duplicates_skipped=duplicate,
    )


@router.put("/{report_id}", response_model=DataResponse[ReportResponse], summary="Update report")
def update_report(
    report_id: int,
    payload: ReportUpdate,
    service: ReportServiceDep,
    current: RequireAdmin,
) -> DataResponse[ReportResponse]:
    """Update report (Admin)."""
    report = service.update_report(report_id, payload, actor=current.name)
    return DataResponse(data=ReportResponse.model_validate(report), message="Report updated")


@router.delete("/{report_id}", response_model=MessageResponse, summary="Delete report")
def delete_report(
    report_id: int,
    service: ReportServiceDep,
    current: RequireAdmin,
) -> MessageResponse:
    """Soft-delete report (Admin)."""
    service.delete_report(report_id, actor=current.name)
    return MessageResponse(message=f"Report {report_id} deleted")
