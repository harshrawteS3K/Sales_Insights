"""Segment-scoped data access for persona / Segment Head users."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.dependencies.rbac import RequestUser
from app.enums import UserRole
from app.repositories.user_segment_repository import UserSegmentRepository


ALL_SEGMENTS = "*"


class SegmentAccessService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_segments = UserSegmentRepository(db)

    def segments_for_user(self, user: RequestUser) -> List[str]:
        """Return assigned segments, or ``['*']`` for unrestricted admin roles."""
        if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            return [ALL_SEGMENTS]
        if user.segments and ALL_SEGMENTS in user.segments:
            return [ALL_SEGMENTS]
        # Prefer DB active assignments so matrix ticks are authoritative
        if user.user_id:
            return self.user_segments.list_for_user(user.user_id)
        if user.segments:
            return list(user.segments)
        return []

    def is_unrestricted(self, user: RequestUser) -> bool:
        segs = self.segments_for_user(user)
        return not segs or ALL_SEGMENTS in segs

    def can_access_segment(self, user: RequestUser, segment: Optional[str]) -> bool:
        if self.is_unrestricted(user):
            return True
        if not segment:
            return False
        allowed = {s.casefold() for s in self.segments_for_user(user)}
        return segment.strip().casefold() in allowed

    def allowed_segments(self, user: RequestUser) -> Optional[list[str]]:
        """
        Return segment scope for SQL filters.

        ``None`` = unrestricted (admin / super admin).
        ``[]`` = no segment access.
        """
        if self.is_unrestricted(user):
            return None
        return [s for s in self.segments_for_user(user) if s != ALL_SEGMENTS]

    def require_segment_access(self, user: RequestUser, segment: Optional[str]) -> None:
        """Raise ``ForbiddenError`` when persona user lacks segment access."""
        from app.exceptions import ForbiddenError

        if self.can_access_segment(user, segment):
            return
        raise ForbiddenError(
            "You do not have access to this segment",
            details={"segment": segment, "allowed": self.segments_for_user(user)},
        )
