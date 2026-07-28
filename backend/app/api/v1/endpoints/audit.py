"""Audit trail endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.dependencies.rbac import RequireAdmin, RequireUser
from app.dependencies.services import AuditServiceDep
from app.schemas.audit import AuditTrailCreate, AuditTrailListResponse, AuditTrailResponse, FrontendAuditLog
from app.schemas.common import DataResponse

router = APIRouter(tags=["Audit Logs"])


@router.get(
    "/audit-trail",
    response_model=List[FrontendAuditLog],
    summary="List audit trail (frontend shape)",
)
def list_audit_trail_frontend(
    service: AuditServiceDep,
    _: RequireUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=10000),
    action: Optional[str] = Query(None),
    user_name: Optional[str] = Query(None),
) -> List[FrontendAuditLog]:
    """GET /api/audit-trail — frontend AuditTrail contract."""
    logs = service.list_logs(skip=skip, limit=limit, action=action, user_name=user_name)
    return service.to_frontend(logs)


@router.get(
    "/audit-logs",
    response_model=AuditTrailListResponse,
    summary="List audit logs (full shape)",
)
def list_audit_logs(
    service: AuditServiceDep,
    _: RequireAdmin,
    skip: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=10000),
    action: Optional[str] = Query(None),
    user_name: Optional[str] = Query(None),
) -> AuditTrailListResponse:
    """Full audit log list (Admin)."""
    logs = service.list_logs(skip=skip, limit=limit, action=action, user_name=user_name)
    return AuditTrailListResponse(
        data=[AuditTrailResponse.model_validate(log) for log in logs],
        total=service.count_logs(action=action, user_name=user_name),
    )


@router.post(
    "/audit-logs",
    response_model=DataResponse[AuditTrailResponse],
    summary="Create audit log entry",
)
def create_audit_log(
    payload: AuditTrailCreate,
    service: AuditServiceDep,
    _: RequireAdmin,
) -> DataResponse[AuditTrailResponse]:
    """Manually create an audit log entry (Admin)."""
    created = service.log(payload)
    return DataResponse(data=AuditTrailResponse.model_validate(created), message="Audit log created")
