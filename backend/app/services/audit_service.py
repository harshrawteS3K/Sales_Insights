"""Centralized enterprise Audit Service."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.enums import AuditAction, AuditModule, AuditStatus
from app.exceptions import NotFoundError
from app.models.audit_trail import AuditTrail
from app.repositories.audit_repository import AuditTrailRepository
from app.schemas.audit import (
    AuditEventCreate,
    AuditTrailCreate,
    AuditTrailPageResponse,
    AuditTrailRow,
    FrontendAuditLog,
)
from app.utils.datetime_utils import format_audit_timestamp
from app.utils.files import ensure_dir

logger = get_logger(__name__)

_ENTITY_MODULE: Dict[str, str] = {
    "customer_master": AuditModule.MASTER_DATA.value,
    "product_master": AuditModule.MASTER_DATA.value,
    "template": AuditModule.MASTER_DATA.value,
    "sync_job": AuditModule.EMAILS.value,
    "email_message": AuditModule.EMAILS.value,
    "report": AuditModule.EMAILS.value,
    "sales_record": AuditModule.CONSOLIDATED.value,
    "consolidated_data": AuditModule.CONSOLIDATED.value,
    "distributor": AuditModule.CONSOLIDATED.value,
    "user": AuditModule.SETTINGS.value,
    "auth": AuditModule.AUTHENTICATION.value,
    "visualization": AuditModule.VISUALIZATION.value,
    "dashboard": AuditModule.DASHBOARD.value,
    "audit_trail": AuditModule.SYSTEM.value,
}


class AuditService:
    """Single entry-point for immutable business-event logging."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditTrailRepository(db)

    @staticmethod
    def _action_value(action: Union[AuditAction, str]) -> str:
        return action.value if hasattr(action, "value") else str(action)

    @staticmethod
    def _infer_module(entity_type: Optional[str], module: Optional[str]) -> Optional[str]:
        if module:
            return module
        if not entity_type:
            return None
        return _ENTITY_MODULE.get(entity_type.strip().lower())

    @staticmethod
    def _infer_status(action: str, status: Optional[str]) -> str:
        if status and status.strip():
            return status.strip()
        lowered = action.lower()
        if "fail" in lowered:
            return AuditStatus.FAILED.value
        if action in (AuditAction.DELETED.value, AuditAction.WARNING.value) or "warning" in lowered:
            return AuditStatus.WARNING.value
        if action in (
            AuditAction.VIEWED.value,
            AuditAction.OPENED.value,
            AuditAction.LOGIN.value,
            AuditAction.LOGOUT.value,
        ) or "login" in lowered or "logout" in lowered or "opened" in lowered:
            return AuditStatus.INFO.value
        return AuditStatus.SUCCESS.value

    def log(self, payload: AuditTrailCreate) -> AuditTrail:
        """Persist an audit trail entry (preferred for service-layer hooks)."""
        action = self._action_value(payload.action)
        entity = AuditTrail(
            user_name=payload.user_name,
            user_role=(payload.user_role or "").strip().lower() or None,
            action=action,
            module=self._infer_module(payload.entity_type, payload.module),
            details=payload.details,
            status=self._infer_status(action, payload.status),
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
            "Audit | action={} | module={} | status={} | user={} | role={}",
            created.action,
            created.module,
            created.status,
            created.user_name,
            created.user_role,
        )
        return created

    def record(
        self,
        *,
        actor: str,
        action: Union[AuditAction, str],
        description: str,
        module: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        report_name: Optional[str] = None,
        user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditTrail:
        """Convenience wrapper used by controllers/services."""
        return self.log(
            AuditTrailCreate(
                user_name=actor,
                user_role=role,
                action=action,
                details=description,
                module=module,
                status=status,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                report_name=report_name,
                user_id=user_id,
                extra_metadata=metadata,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

    def log_client_event(
        self,
        payload: AuditEventCreate,
        *,
        actor: str,
        role: Optional[str] = None,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditTrail:
        """Record a meaningful UI/auth event from the client."""
        return self.record(
            actor=actor,
            role=role,
            action=payload.action,
            description=payload.description,
            module=payload.module,
            status=payload.status,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            report_name=payload.report_name,
            user_id=user_id,
            metadata=payload.metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def get(self, audit_id: int) -> AuditTrail:
        """Fetch one audit row or raise NotFoundError."""
        entity = self.repo.get_by_id(audit_id, include_deleted=True)
        if entity is None:
            raise NotFoundError(f"Audit entry {audit_id} not found")
        return entity

    def list_logs(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
        search: Optional[str] = None,
        role: Optional[str] = None,
        module: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[AuditTrail]:
        """List audit logs (newest first)."""
        return self.repo.list_recent(
            skip=skip,
            limit=limit,
            action=action,
            user_name=user_name,
            search=search,
            role=role,
            module=module,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

    def count_logs(
        self,
        *,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
        search: Optional[str] = None,
        role: Optional[str] = None,
        module: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> int:
        """Return total audit logs matching filters."""
        return self.repo.count_recent(
            action=action,
            user_name=user_name,
            search=search,
            role=role,
            module=module,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

    def list_page(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
        role: Optional[str] = None,
        module: Optional[str] = None,
        status: Optional[str] = None,
        action: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> AuditTrailPageResponse:
        """Server-side paginated enterprise list."""
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 25), 200))
        total = self.count_logs(
            search=search,
            role=role,
            module=module,
            status=status,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )
        total_pages = (total + page_size - 1) // page_size if total else 0
        skip = (page - 1) * page_size
        rows = self.list_logs(
            skip=skip,
            limit=page_size,
            search=search,
            role=role,
            module=module,
            status=status,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )
        return AuditTrailPageResponse(
            data=[self.to_row(item) for item in rows],
            total=total,
            page=page,
            pageSize=page_size,
            totalPages=total_pages,
        )

    def to_row(self, item: AuditTrail) -> AuditTrailRow:
        """Map ORM → enterprise UI row."""
        return AuditTrailRow(
            id=item.id,
            timestamp=format_audit_timestamp(item.created_at),
            user=item.user_name,
            role=item.user_role,
            module=item.module,
            action=item.action,
            description=item.details,
            status=item.status or AuditStatus.SUCCESS.value,
            entityType=item.entity_type,
            entityId=item.entity_id,
            reportName=item.report_name,
            ipAddress=item.ip_address,
            userAgent=item.user_agent,
            metadata=item.extra_metadata,
            createdAt=item.created_at,
        )

    def to_frontend(self, logs: List[AuditTrail]) -> List[FrontendAuditLog]:
        """Legacy frontend mapper."""
        return [
            FrontendAuditLog(
                id=str(item.id),
                user=item.user_name,
                action=item.action,
                details=item.details,
                timestamp=format_audit_timestamp(item.created_at),
                reportName=item.report_name,
                role=item.user_role,
                module=item.module,
                status=item.status,
            )
            for item in logs
        ]

    def export_excel(
        self,
        *,
        search: Optional[str] = None,
        role: Optional[str] = None,
        module: Optional[str] = None,
        status: Optional[str] = None,
        action: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        max_rows: int = 10000,
    ) -> Path:
        """Export filtered audit rows to Excel (capped for safety)."""
        rows = self.list_logs(
            skip=0,
            limit=max_rows,
            search=search,
            role=role,
            module=module,
            status=status,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )
        wb = Workbook()
        ws = wb.active
        ws.title = "Audit Trail"
        ws.append(
            [
                "Timestamp",
                "User",
                "Role",
                "Module",
                "Action",
                "Description",
                "Status",
                "Entity Type",
                "Entity ID",
            ]
        )
        for item in rows:
            ws.append(
                [
                    format_audit_timestamp(item.created_at),
                    item.user_name,
                    item.user_role or "",
                    item.module or "",
                    item.action,
                    item.details,
                    item.status or "",
                    item.entity_type or "",
                    item.entity_id or "",
                ]
            )
        out_dir = Path(settings.download_dir) / "audit_exports"
        ensure_dir(out_dir)
        path = out_dir / f"audit_trail_{date.today().isoformat()}.xlsx"
        wb.save(path)
        return path
