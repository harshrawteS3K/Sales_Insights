"""Audit trail repository."""

from typing import List, Optional

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.audit_trail import AuditTrail
from app.repositories.base import BaseRepository


class AuditTrailRepository(BaseRepository[AuditTrail]):
    """Data access for audit trail entries."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, AuditTrail)

    def _filtered_query(
        self,
        *,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> Select:
        """Build a filtered audit query."""
        query = select(AuditTrail)
        if action:
            query = query.where(AuditTrail.action == action)
        if user_name:
            query = query.where(AuditTrail.user_name.ilike(f"%{user_name}%"))
        return query

    def list_recent(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[AuditTrail]:
        """List recent audit entries with optional filters."""
        query = self._filtered_query(action=action, user_name=user_name)
        query = query.order_by(AuditTrail.created_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(query).all())

    def count_recent(
        self,
        *,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> int:
        """Count audit entries matching optional filters."""
        filtered = self._filtered_query(action=action, user_name=user_name)
        query = select(func.count()).select_from(filtered.subquery())
        return int(self.db.scalar(query) or 0)
