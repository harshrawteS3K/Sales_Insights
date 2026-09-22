"""Global Access Control Mode (segment vs distributor)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies.rbac import RequestUser
from app.enums import UserRole
from app.models.system_setting import SystemSetting
from app.repositories.user_distributor_repository import UserDistributorRepository
from app.repositories.user_segment_repository import UserSegmentRepository

ACCESS_MODE_KEY = "access_mode"
MODE_SEGMENT = "segment"
MODE_DISTRIBUTOR = "distributor"
VALID_MODES = {MODE_SEGMENT, MODE_DISTRIBUTOR}


@dataclass
class DataScope:
    """Resolved data filter for a request user.

    ``None`` on a field means unrestricted for that dimension.
    Empty list means no access for that dimension.
    """

    allowed_segments: Optional[List[str]] = None
    allowed_distributor_ids: Optional[List[int]] = None
    allowed_companies: Optional[List[str]] = None
    access_mode: str = MODE_SEGMENT
    unrestricted: bool = False


class AccessControlService:
    """Read/write global access mode and resolve per-user data scope."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_segments = UserSegmentRepository(db)
        self.user_distributors = UserDistributorRepository(db)

    def get_access_mode(self) -> str:
        row = self.db.get(SystemSetting, ACCESS_MODE_KEY)
        if row is None:
            return MODE_SEGMENT
        value = (row.value or MODE_SEGMENT).strip().lower()
        return value if value in VALID_MODES else MODE_SEGMENT

    def set_access_mode(self, mode: str, *, actor: str = "admin") -> str:
        cleaned = (mode or "").strip().lower()
        if cleaned not in VALID_MODES:
            from app.exceptions import ValidationAppError

            raise ValidationAppError(
                f"access_mode must be '{MODE_SEGMENT}' or '{MODE_DISTRIBUTOR}'",
                details={"mode": mode},
            )
        row = self.db.get(SystemSetting, ACCESS_MODE_KEY)
        if row is None:
            self.db.add(SystemSetting(key=ACCESS_MODE_KEY, value=cleaned))
        else:
            row.value = cleaned
        self.db.flush()
        from app.schemas.audit import AuditTrailCreate
        from app.services.audit_service import AuditService
        from app.enums import AuditAction, AuditModule, AuditStatus

        AuditService(self.db).log(
            AuditTrailCreate(
                user_name=actor,
                user_role=UserRole.ADMIN.value,
                action=AuditAction.UPDATED,
                details=f"Access Control Mode set to '{cleaned}'",
                module=AuditModule.USER_MANAGEMENT.value,
                status=AuditStatus.SUCCESS.value,
                entity_type="system_setting",
                entity_id=ACCESS_MODE_KEY,
                extra_metadata={"access_mode": cleaned},
            )
        )
        return cleaned

    def resolve_scope(self, user: RequestUser) -> DataScope:
        mode = self.get_access_mode()
        if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            return DataScope(
                allowed_segments=None,
                allowed_distributor_ids=None,
                allowed_companies=None,
                access_mode=mode,
                unrestricted=True,
            )

        segments = list(user.segments or [])
        if user.user_id:
            # Prefer DB visibility (active OR retain_history) over session header
            # so historical retention survives logout / stale session segments.
            segments = self.user_segments.list_visible_segments_for_user(user.user_id)
        segments = [s for s in segments if s and s != "*"]

        if mode == MODE_DISTRIBUTOR:
            dist_ids: List[int] = []
            companies: List[str] = []
            if user.user_id:
                dist_ids = self.user_distributors.list_ids_for_user(user.user_id)
                companies = self.user_distributors.list_companies_for_user(user.user_id)
            return DataScope(
                allowed_segments=None,
                allowed_distributor_ids=dist_ids,
                allowed_companies=companies,
                access_mode=mode,
                unrestricted=False,
            )

        # Segment mode (default)
        return DataScope(
            allowed_segments=segments,
            allowed_distributor_ids=None,
            allowed_companies=None,
            access_mode=mode,
            unrestricted=False,
        )
