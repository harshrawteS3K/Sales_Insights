"""Audit trail schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.enums import AuditAction
from app.schemas.common import TimestampSchema


class AuditTrailCreate(BaseModel):
    """Create audit log payload."""

    user_name: str = Field(..., min_length=1, max_length=255)
    action: AuditAction
    details: str
    report_name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class AuditTrailResponse(TimestampSchema):
    """Audit trail API response."""

    id: int
    user_name: str
    action: str
    details: str
    report_name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class FrontendAuditLog(BaseModel):
    """Frontend AuditTrail shape: GET /api/audit-trail."""

    id: str
    user: str
    action: str
    details: str
    timestamp: str
    reportName: Optional[str] = None


class AuditTrailListResponse(BaseModel):
    """List of audit logs."""

    success: bool = True
    data: List[AuditTrailResponse]
    total: int
