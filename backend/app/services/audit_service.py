"""Audit trail service."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.audit_trail import AuditTrail
from app.repositories.audit_repository import AuditTrailRepository
from app.schemas.audit import AuditTrailCreate, FrontendAuditLog
from app.utils.datetime_utils import format_audit_timestamp

logger = get_logger(__name__)


class AuditService:
    """Business logic for audit logging."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditTrailRepository(db)

    def log(self, payload: AuditTrailCreate) -> AuditTrail:
        """Persist an audit trail entry."""
        action = payload.action.value if hasattr(payload.action, "value") else str(payload.action)
        entity = AuditTrail(
            user_name=payload.user_name,
            action=action,
            details=payload.details,
            report_name=payload.report_name,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            user_id=payload.user_id,
            ip_address=payload.ip_address,
            user_agent=payload.user_agent,
            extra_metadata=payload.extra_metadata,
        )
        created = self.repo.create(entity)
        logger.info(
            "Audit | action={} | user={} | details={}",
            created.action,
            created.user_name,
            created.details,
        )
        return created

    def list_logs(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[AuditTrail]:
        """List audit logs."""
        return self.repo.list_recent(
            skip=skip,
            limit=limit,
            action=action,
            user_name=user_name,
        )

    def count_logs(
        self,
        *,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> int:
        """Return total audit logs matching the same filters as list_logs."""
        return self.repo.count_recent(action=action, user_name=user_name)

    def to_frontend(self, logs: List[AuditTrail]) -> List[FrontendAuditLog]:
        """Map ORM audit rows to frontend AuditLog shape."""
        return [
            FrontendAuditLog(
                id=str(item.id),
                user=item.user_name,
                action=item.action,
                details=item.details,
                timestamp=format_audit_timestamp(item.created_at),
                reportName=item.report_name,
            )
            for item in logs
        ]
