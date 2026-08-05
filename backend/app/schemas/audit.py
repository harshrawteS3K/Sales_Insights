"""Audit trail schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.enums import AuditAction, AuditModule, AuditStatus
from app.schemas.common import TimestampSchema


class AuditTrailCreate(BaseModel):
    """Create audit log payload (server-side services)."""

    user_name: str = Field(..., min_length=1, max_length=255)
    action: AuditAction | str
    details: str  # description
    user_role: Optional[str] = None
    module: Optional[str] = None
    status: Optional[str] = None
    report_name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class AuditEventCreate(BaseModel):
    """Client-reported meaningful business event (login, view opened, etc.)."""

    action: str = Field(..., min_length=1, max_length=80)
    module: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1)
    status: str = Field(default=AuditStatus.SUCCESS.value, max_length=20)
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    report_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AuditTrailResponse(TimestampSchema):
    """Full audit trail API response."""

    id: int
    user_name: str
    user_role: Optional[str] = None
    action: str
    module: Optional[str] = None
    details: str
    status: str = AuditStatus.SUCCESS.value
    report_name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class AuditTrailRow(BaseModel):
    """Enterprise UI row shape."""

    id: int
    timestamp: str
    user: str
    role: Optional[str] = None
    module: Optional[str] = None
    action: str
    description: str
    status: str
    entityType: Optional[str] = None
    entityId: Optional[str] = None
    reportName: Optional[str] = None
    ipAddress: Optional[str] = None
    userAgent: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    createdAt: Optional[datetime] = None


class AuditTrailPageResponse(BaseModel):
    """Paginated enterprise audit list."""

    success: bool = True
    data: List[AuditTrailRow] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    pageSize: int = 25
    totalPages: int = 0


class FrontendAuditLog(BaseModel):
    """Legacy frontend shape (compat)."""

    id: str
    user: str
    action: str
    details: str
    timestamp: str
    reportName: Optional[str] = None
    role: Optional[str] = None
    module: Optional[str] = None
    status: Optional[str] = None


class AuditTrailListResponse(BaseModel):
    """List of audit logs (full ORM shape)."""

    success: bool = True
    data: List[AuditTrailResponse]
    total: int
