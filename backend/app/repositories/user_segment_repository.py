"""UserSegment repository for segment-based RBAC mapping."""

from typing import List, Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.distributor import Distributor
from app.models.user_segment import UserSegment

ALL_SEGMENTS = ["Paper", "Carpet", "Construction", "Rubber", "Gloves"]


class UserSegmentRepository:
    """Repository managing user_segments table for Segment RBAC."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_segments_for_user(self, user_id: int) -> List[str]:
        """Return actively assigned segment names (matrix ticks / live access)."""
        stmt = (
            select(UserSegment.segment)
            .where(
                UserSegment.user_id == user_id,
                UserSegment.active.is_(True),
            )
            .order_by(UserSegment.segment.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_for_user(self, user_id: int) -> List[str]:
        """Alias used by auth / segment access services (active only)."""
        return self.list_segments_for_user(user_id)

    def list_visible_segments_for_user(self, user_id: int) -> List[str]:
        """Segments the user may see in data views (active OR retain_history)."""
        stmt = (
            select(UserSegment.segment)
            .where(
                UserSegment.user_id == user_id,
                or_(
                    UserSegment.active.is_(True),
                    UserSegment.retain_history.is_(True),
                ),
            )
            .order_by(UserSegment.segment.asc())
        )
        return list(self.db.scalars(stmt).all())

    def assign_segments_to_user(
        self,
        user_id: int,
        segments: List[str],
        *,
        assigned_by: Optional[int] = None,
    ) -> List[str]:
        """Replace user's assigned segments with given list (all active)."""
        self.db.execute(delete(UserSegment).where(UserSegment.user_id == user_id))
        self.db.flush()

        clean_segments = sorted(
            {s.strip() for s in segments if s and s.strip()},
            key=str.casefold,
        )
        for seg in clean_segments:
            entry = UserSegment(
                user_id=user_id,
                segment=seg,
                assigned_by=assigned_by,
                active=True,
                retain_history=False,
            )
            self.db.add(entry)
        self.db.flush()
        return clean_segments

    def replace_for_user(
        self,
        user_id: int,
        segments: List[str],
        *,
        assigned_by: Optional[int] = None,
    ) -> List[str]:
        """Alias for assign_segments_to_user."""
        return self.assign_segments_to_user(user_id, segments, assigned_by=assigned_by)

    def toggle_user_segment(
        self,
        user_id: int,
        segment: str,
        enabled: bool,
        *,
        assigned_by: Optional[int] = None,
        retain_history: Optional[bool] = None,
    ) -> List[str]:
        """
        Tick → active=True (immediate assign).
        Untick → active=False; retain_history from confirmation choice.
        """
        seg_clean = segment.strip()
        if not seg_clean:
            return self.list_segments_for_user(user_id)

        existing = self.db.scalar(
            select(UserSegment).where(
                UserSegment.user_id == user_id,
                UserSegment.segment == seg_clean,
            )
        )

        if enabled:
            if existing:
                existing.active = True
                existing.retain_history = False
                if assigned_by is not None:
                    existing.assigned_by = assigned_by
            else:
                self.db.add(
                    UserSegment(
                        user_id=user_id,
                        segment=seg_clean,
                        assigned_by=assigned_by,
                        active=True,
                        retain_history=False,
                    )
                )
        else:
            keep_history = bool(retain_history) if retain_history is not None else False
            if existing:
                existing.active = False
                existing.retain_history = keep_history
                if assigned_by is not None:
                    existing.assigned_by = assigned_by
            elif keep_history:
                # No prior row — nothing to retain
                pass

        self.db.flush()
        return self.list_segments_for_user(user_id)

    def list_distributor_companies_for_segments(self, segments: List[str]) -> List[str]:
        """Return companies that have sales in any of the given segments."""
        if not segments:
            return []
        from app.models.sales_record import SalesRecord

        clean = [s.strip().casefold() for s in segments if (s or "").strip()]
        if not clean:
            return []
        query = (
            select(Distributor.company, Distributor.name)
            .join(SalesRecord, SalesRecord.distributor_id == Distributor.id)
            .where(
                Distributor.is_deleted.is_(False),
                SalesRecord.is_deleted.is_(False),
                func.lower(SalesRecord.segment).in_(clean),
            )
        )
        result: set[str] = set()
        for company, name in self.db.execute(query).all():
            if company and company.strip():
                result.add(company.strip())
            elif name and name.strip():
                result.add(name.strip())
        return sorted(result)

    def list_distributor_ids_for_segments(self, segments: List[str]) -> List[int]:
        """Return distributor IDs that have sales in any of the given segments."""
        if not segments:
            return []
        from app.models.sales_record import SalesRecord

        clean = [s.strip().casefold() for s in segments if (s or "").strip()]
        if not clean:
            return []
        query = (
            select(Distributor.id)
            .join(SalesRecord, SalesRecord.distributor_id == Distributor.id)
            .where(
                Distributor.is_deleted.is_(False),
                SalesRecord.is_deleted.is_(False),
                func.lower(SalesRecord.segment).in_(clean),
            )
            .distinct()
        )
        return sorted(int(i) for i in self.db.scalars(query).all())
