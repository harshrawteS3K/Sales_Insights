"""Report repository."""

from typing import List, Optional

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.report import Report
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[Report]):
    """Data access for reports."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Report)

    def get_by_content_hash(self, content_hash: str) -> Optional[Report]:
        """Find an active report by exact Excel content hash (file duplicate only)."""
        query = select(Report).where(
            Report.content_hash == content_hash,
            Report.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def get_active_by_business_key(
        self, distributor_id: int, reporting_month: str
    ) -> Optional[Report]:
        """Find the active report for Distributor + Reporting Month."""
        from app.utils.reporting_month import normalize_reporting_month

        month = normalize_reporting_month(reporting_month)
        query = select(Report).where(
            Report.distributor_id == distributor_id,
            Report.reporting_month == month,
            Report.is_deleted.is_(False),
        )
        found = self.db.scalar(query)
        if found:
            return found
        # Fallback: match any active report whose month normalizes to the same key
        # (handles legacy datetime strings like ``2026-07-01 00:00:00``)
        candidates = list(
            self.db.scalars(
                select(Report).where(
                    Report.distributor_id == distributor_id,
                    Report.is_deleted.is_(False),
                    Report.reporting_month.is_not(None),
                )
            ).all()
        )
        for report in candidates:
            if normalize_reporting_month(report.reporting_month) == month:
                return report
        return None

    def list_active_for_distributor(self, distributor_id: int) -> List[Report]:
        """All active reports for a distributor (for replacement sweep)."""
        query = select(Report).where(
            Report.distributor_id == distributor_id,
            Report.is_deleted.is_(False),
        )
        return list(self.db.scalars(query).all())

    def get_by_public_id(self, public_id: str) -> Optional[Report]:
        """Fetch report by public UUID."""
        query = (
            select(Report)
            .options(selectinload(Report.sales_records))
            .where(Report.public_id == public_id, Report.is_deleted.is_(False))
        )
        return self.db.scalar(query)

    def _filtered_query(
        self,
        *,
        status: Optional[str] = None,
        source: Optional[str] = None,
        report_type: Optional[str] = None,
        distributor_id: Optional[int] = None,
    ) -> Select:
        """Build a filtered query for active reports."""
        query = select(Report).where(Report.is_deleted.is_(False))
        if status:
            query = query.where(Report.status == status)
        if source:
            query = query.where(Report.source == source)
        if report_type:
            query = query.where(Report.report_type == report_type)
        if distributor_id:
            query = query.where(Report.distributor_id == distributor_id)
        return query

    def list_with_filters(
        self,
        *,
        status: Optional[str] = None,
        source: Optional[str] = None,
        report_type: Optional[str] = None,
        distributor_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Report]:
        """List reports with optional filters."""
        query = self._filtered_query(
            status=status,
            source=source,
            report_type=report_type,
            distributor_id=distributor_id,
        )
        query = query.order_by(Report.created_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(query).all())

    def count_with_filters(
        self,
        *,
        status: Optional[str] = None,
        source: Optional[str] = None,
        report_type: Optional[str] = None,
        distributor_id: Optional[int] = None,
    ) -> int:
        """Count reports matching optional filters."""
        filtered = self._filtered_query(
            status=status,
            source=source,
            report_type=report_type,
            distributor_id=distributor_id,
        )
        query = select(func.count()).select_from(filtered.subquery())
        return int(self.db.scalar(query) or 0)

    def count_by_status(self, status: str) -> int:
        """Count reports by status."""
        query = select(func.count()).select_from(Report).where(
            Report.is_deleted.is_(False),
            Report.status == status,
        )
        return int(self.db.scalar(query) or 0)
