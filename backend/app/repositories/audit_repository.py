"""Audit trail repository — server-side filter + pagination."""

from datetime import date, datetime, time, timezone
from typing import List, Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.audit_trail import AuditTrail
from app.repositories.base import BaseRepository


class AuditTrailRepository(BaseRepository[AuditTrail]):
    """Data access for audit trail entries (immutable append-only)."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, AuditTrail)

    def _filtered_query(
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
    ) -> Select:
        """Build a filtered audit query (never soft-deletes — logs are immutable)."""
        query = select(AuditTrail)
        if action and action.lower() != "all":
            query = query.where(AuditTrail.action == action)
        if user_name:
            query = query.where(AuditTrail.user_name.ilike(f"%{user_name.strip()}%"))
        if role and role.lower() != "all":
            query = query.where(func.lower(AuditTrail.user_role) == role.strip().lower())
        if module and module.lower() != "all":
            query = query.where(func.lower(AuditTrail.module) == module.strip().lower())
        if status and status.lower() != "all":
            query = query.where(func.lower(AuditTrail.status) == status.strip().lower())
        if date_from:
            start = datetime.combine(date_from, time.min).replace(tzinfo=timezone.utc)
            query = query.where(AuditTrail.created_at >= start)
        if date_to:
            end = datetime.combine(date_to, time.max).replace(tzinfo=timezone.utc)
            query = query.where(AuditTrail.created_at <= end)
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(AuditTrail.user_name).like(term),
                    func.lower(AuditTrail.action).like(term),
                    func.lower(func.coalesce(AuditTrail.module, "")).like(term),
                    func.lower(AuditTrail.details).like(term),
                    func.lower(func.coalesce(AuditTrail.report_name, "")).like(term),
                )
            )
        return query

    def list_recent(
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
        """List recent audit entries with optional filters (newest first)."""
        query = self._filtered_query(
            action=action,
            user_name=user_name,
            search=search,
            role=role,
            module=module,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        query = query.order_by(AuditTrail.created_at.desc(), AuditTrail.id.desc())
        query = query.offset(skip).limit(limit)
        return list(self.db.scalars(query).all())

    def count_recent(
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
        """Count audit entries matching filters."""
        filtered = self._filtered_query(
            action=action,
            user_name=user_name,
            search=search,
            role=role,
            module=module,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        query = select(func.count()).select_from(filtered.subquery())
        return int(self.db.scalar(query) or 0)
