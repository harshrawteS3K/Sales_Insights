"""Enterprise Audit Trail endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from app.dependencies.rbac import RequireAdmin, RequireUser
from app.dependencies.services import AuditServiceDep
from app.enums import AuditModule, AuditStatus
from app.schemas.audit import (
    AuditEventCreate,
    AuditTrailPageResponse,
    AuditTrailResponse,
    AuditTrailRow,
)
from app.schemas.common import DataResponse

router = APIRouter(prefix="/audit-trail", tags=["Audit Trail"])


def _client_meta(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    ua = request.headers.get("User-Agent")
    return ip, ua


@router.get(
    "",
    response_model=AuditTrailPageResponse,
    summary="Paginated enterprise audit trail (Admin)",
)
def list_audit_trail(
    service: AuditServiceDep,
    _: RequireAdmin,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None, description="admin | user"),
    module: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
) -> AuditTrailPageResponse:
    """GET /api/audit-trail — server-side search, filters, pagination."""
    return service.list_page(
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        module=module,
        status=status,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/export",
    summary="Export filtered audit trail to Excel (Admin)",
)
def export_audit_trail(
    service: AuditServiceDep,
    current: RequireAdmin,
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
) -> FileResponse:
    """Export respects current filters; capped at 10k rows."""
    path = service.export_excel(
        search=search,
        role=role,
        module=module,
        status=status,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    service.record(
        actor=current.name,
        role=current.role.value if hasattr(current.role, "value") else str(current.role),
        action="Exported",
        description="Exported Audit Trail to Excel",
        module=AuditModule.SYSTEM.value,
        status=AuditStatus.SUCCESS.value,
        entity_type="audit_trail",
    )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@router.post(
    "/events",
    response_model=DataResponse[AuditTrailResponse],
    summary="Record a meaningful client business event",
)
def create_audit_event(
    payload: AuditEventCreate,
    service: AuditServiceDep,
    current: RequireUser,
    request: Request,
) -> DataResponse[AuditTrailResponse]:
    """
    POST /api/audit-trail/events

    Used for Login/Logout and intentional UI events (not page navigation noise).
    """
    ip, ua = _client_meta(request)
    created = service.log_client_event(
        payload,
        actor=current.name,
        role=current.role.value if hasattr(current.role, "value") else str(current.role),
        user_id=current.user_id,
        ip_address=ip,
        user_agent=ua,
    )
    return DataResponse(
        data=AuditTrailResponse.model_validate(created),
        message="Audit event recorded",
    )


@router.get(
    "/{audit_id}",
    response_model=DataResponse[AuditTrailRow],
    summary="Get one audit entry (Admin)",
)
def get_audit_entry(
    audit_id: int,
    service: AuditServiceDep,
    _: RequireAdmin,
) -> DataResponse[AuditTrailRow]:
    """GET /api/audit-trail/{id}"""
    item = service.get(audit_id)
    return DataResponse(data=service.to_row(item))
