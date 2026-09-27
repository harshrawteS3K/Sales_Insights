"""Financial-year and quarter duplicate review."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.enums import AuditAction, EmailProcessStatus, ReportSource
from app.erp_parser.confidence import compute_erp_confidence
from app.erp_parser.header_detector import detect_header_row
from app.erp_parser.header_mapper import FIELD_DISPLAY, normalize_header_text
from app.erp_parser.row_extractor import extract_rows
from app.erp_parser.sheet_detector import detect_best_sheet
from app.erp_parser.workbook_detector import read_sheet_matrix
from app.exceptions import ExcelProcessingError, ValidationAppError
from app.schemas.audit import AuditTrailCreate
from app.schemas.sales_record import ParsedSalesRow
from app.services.erp_ingest.constants import (
    DUPLICATE_REVIEW_MESSAGE,
    MAX_EXCEL_ATTACHMENTS_PER_EMAIL,
    MIN_IMPORT_ACCURACY,
    _normalize_mapped_field,
    logger,
)
from app.services.report_service import DUPLICATE_SUBMISSION_MESSAGE
from app.utils.hashing import build_sales_row_hash
from app.utils.quantity import format_quantity, parse_quantity

class DuplicateMixin:
    def _drop_existing_business_rows(
        self,
        distributor_id: int,
        period: str,
        rows: List[ParsedSalesRow],
    ) -> List[ParsedSalesRow]:
        """Drop rows that already exist for this distributor, place, and quarter."""
        from sqlalchemy import select

        from app.models.report import Report
        from app.models.sales_record import SalesRecord
        from app.utils.reporting_month import normalize_reporting_month

        period_key = normalize_reporting_month(period) or (period or "").strip()
        existing = self.db.execute(
            select(
                SalesRecord.customer_name,
                SalesRecord.product,
                SalesRecord.quantity,
                SalesRecord.location,
                SalesRecord.segment,
            )
            .join(Report, Report.id == SalesRecord.report_id)
            .where(
                SalesRecord.is_deleted.is_(False),
                Report.is_deleted.is_(False),
                SalesRecord.distributor_id == distributor_id,
                Report.reporting_month == period_key,
            )
        ).all()
        seen = {
            (
                str(customer or "").strip().casefold(),
                str(product or "").strip().casefold(),
                self._business_qty(qty),
                str(loc or "").strip().casefold(),
                str(seg or "").strip().casefold(),
            )
            for customer, product, qty, loc, seg in existing
        }
        fresh: List[ParsedSalesRow] = []
        for row in rows:
            key = (
                row.customer_name.strip().casefold(),
                row.product.strip().casefold(),
                self._business_qty(row.quantity),
                (row.location or "").strip().casefold(),
                (row.segment or "").strip().casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            fresh.append(row)
        return fresh

    def _period_scope_filters(
        self,
        distributor_id: int,
        period: str,
        segment: str,
        location: str,
    ) -> Tuple[str, List[Any]]:
        from sqlalchemy import func

        from app.models.report import Report
        from app.models.sales_record import SalesRecord
        from app.repositories.sales_record_repository import reporting_month_expr
        from app.utils.reporting_month import normalize_reporting_month

        period_key = normalize_reporting_month(period) or (period or "").strip()
        filters: List[Any] = [
            SalesRecord.is_deleted.is_(False),
            Report.is_deleted.is_(False),
            SalesRecord.distributor_id == distributor_id,
            reporting_month_expr() == period_key,
        ]
        if (segment or "").strip():
            filters.append(
                func.lower(func.trim(SalesRecord.segment)) == segment.strip().lower()
            )
        if (location or "").strip():
            filters.append(
                func.lower(func.trim(SalesRecord.location)) == location.strip().lower()
            )
        return period_key, filters

    def _count_period_scope(
        self,
        distributor_id: int,
        period: str,
        segment: str,
        location: str,
    ) -> int:
        from sqlalchemy import func, select

        from app.models.report import Report
        from app.models.sales_record import SalesRecord

        _period_key, filters = self._period_scope_filters(
            distributor_id, period, segment, location
        )
        query = (
            select(func.count(SalesRecord.id))
            .select_from(SalesRecord)
            .join(Report, Report.id == SalesRecord.report_id)
            .where(*filters)
        )
        return int(self.db.scalar(query) or 0)

    def _review_hit(
        self,
        *,
        company: str,
        period: str,
        existing_rows: int,
        new_rows: int,
    ) -> Dict[str, Any]:
        from app.utils.period_calendar import fy_short_display, parse_quarter_label

        spec = parse_quarter_label(period)
        financial_year = fy_short_display(spec.year) if spec and spec.year else period
        quarter = f"Q{spec.quarter}" if spec and spec.quarter else ""
        return {
            "period": period,
            "financial_year": financial_year,
            "quarter": quarter,
            "existing_rows": existing_rows,
            "new_rows": new_rows,
            "distributor": company,
        }

    def _combine_duplicate_review(
        self, company: str, hits: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not hits:
            return None
        quarters: List[str] = []
        for hit in hits:
            label = str(hit.get("quarter") or "").strip()
            if label and label not in quarters:
                quarters.append(label)
        return {
            "detected": True,
            "message": DUPLICATE_REVIEW_MESSAGE,
            "distributor": company,
            "financial_year": hits[0].get("financial_year") or "",
            "quarter": ", ".join(quarters),
            "existing_rows": sum(int(hit.get("existing_rows") or 0) for hit in hits),
            "new_rows": sum(int(hit.get("new_rows") or 0) for hit in hits),
            "periods": [str(hit.get("period") or "") for hit in hits if hit.get("period")],
        }

    def _duplicate_hits_for_periods(
        self,
        *,
        distributor_id: int,
        company: str,
        segment: str,
        location: str,
        counts_by_period: Dict[str, int],
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for period, new_rows in counts_by_period.items():
            if not period or new_rows <= 0:
                continue
            existing = self._count_period_scope(
                distributor_id, period, segment, location
            )
            if existing <= 0:
                continue
            hits.append(
                self._review_hit(
                    company=company,
                    period=period,
                    existing_rows=existing,
                    new_rows=new_rows,
                )
            )
        return hits

    def _replace_period_scope(
        self,
        *,
        distributor_id: int,
        company: str,
        period: str,
        segment: str,
        location: str,
        existing_rows: int,
        new_rows: int,
        actor: str,
    ) -> int:
        from datetime import datetime, timezone

        from sqlalchemy import select

        from app.models.report import Report
        from app.models.sales_record import SalesRecord

        _period_key, filters = self._period_scope_filters(
            distributor_id, period, segment, location
        )
        rows = list(
            self.db.scalars(
                select(SalesRecord)
                .join(Report, Report.id == SalesRecord.report_id)
                .where(*filters)
            ).all()
        )
        now = datetime.now(timezone.utc)
        for row in rows:
            row.row_hash = f"replaced:{row.id}"
            row.is_deleted = True
            row.deleted_at = now
        self.db.flush()
        hit = self._review_hit(
            company=company,
            period=period,
            existing_rows=existing_rows or len(rows),
            new_rows=new_rows,
        )
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.REPLACED,
                details=(
                    "Duplicate Review\n"
                    f"Distributor : {company}\n"
                    f"FY : {hit['financial_year']}\n"
                    f"Quarter : {hit['quarter']}\n"
                    f"Existing Rows : {hit['existing_rows']}\n"
                    f"New Rows : {hit['new_rows']}\n"
                    f"Action : Replaced by {actor}"
                ),
                entity_type="report",
                module="Consolidated Data",
                status="Success",
                extra_metadata={
                    "distributor_id": distributor_id,
                    "period": period,
                    "segment": segment,
                    "location": location,
                    "existing_rows": hit["existing_rows"],
                    "new_rows": hit["new_rows"],
                    "action": f"Replaced by {actor}",
                },
            )
        )
        return len(rows)

    def _recount_report_rows(self, report: Any) -> None:
        from sqlalchemy import func, select

        from app.models.sales_record import SalesRecord

        if report is None:
            return
        active = self.db.scalar(
            select(func.count(SalesRecord.id)).where(
                SalesRecord.report_id == report.id,
                SalesRecord.is_deleted.is_(False),
            )
        )
        report.record_count = int(active or 0)
        self.db.flush()

