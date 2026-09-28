"""Approved import and skip."""

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

class ImportMixin:
    def _persist_preview_rows(
        self,
        *,
        email: Any,
        att: Any,
        preview: Dict[str, Any],
        use_rows: List[Dict[str, Any]],
        distributor_id: int,
        company: str,
        quarter: str,
        segment: str,
        location: str,
        source_unit: str = "MT",
        actor: str,
        fiscal_year_start: Optional[int],
        overall: float,
        replace_existing: bool = False,
    ) -> Tuple[int, bool, Any, List[str], int, Optional[Dict[str, Any]]]:
        """Persist rows. Duplicate scope returns a review payload and writes nothing."""
        path = Path(att.file_path)
        by_period = self._rows_by_period(
            use_rows,
            company=company,
            quarter=quarter,
            segment=segment,
            location=location,
            source_unit=source_unit or "MT",
        )
        if not by_period:
            raise ValidationAppError(
                f"No valid rows to import after validation ({att.file_name})"
            )
        counts = {period: len(rows) for period, rows in by_period.items()}
        hits = self._duplicate_hits_for_periods(
            distributor_id=distributor_id,
            company=company,
            segment=segment,
            location=location,
            counts_by_period=counts,
        )
        review = self._combine_duplicate_review(company, hits)
        if review and not replace_existing:
            return 0, True, None, [], 0, review
        if review and replace_existing:
            for hit in hits:
                self._replace_period_scope(
                    distributor_id=distributor_id,
                    company=company,
                    period=str(hit["period"]),
                    segment=segment,
                    location=location,
                    existing_rows=int(hit["existing_rows"]),
                    new_rows=int(hit["new_rows"]),
                    actor=actor,
                )
        elif not replace_existing:
            incoming = sum(counts.values())
            kept: Dict[str, List[ParsedSalesRow]] = {}
            for period, parsed in by_period.items():
                fresh = self._drop_existing_business_rows(
                    distributor_id,
                    period,
                    parsed,
                )
                if fresh:
                    kept[period] = fresh
            if incoming and not kept:
                only = next(iter(by_period))
                review = self._combine_duplicate_review(
                    company,
                    [
                        self._review_hit(
                            company=company,
                            period=only,
                            existing_rows=incoming,
                            new_rows=incoming,
                        )
                    ],
                )
                return 0, True, None, [], 0, review
            by_period = kept

        total_inserted = 0
        any_dup = False
        last_report = None
        quarters_imported: List[str] = []
        for period, parsed in sorted(by_period.items()):
            try:
                report, inserted, was_dup, _quality = self.reports.persist_approved_rows(
                    path,
                    parsed,
                    quality_score=int(round(overall)),
                    source=ReportSource.OUTLOOK,
                    report_name=email.subject or att.file_name,
                    email_message_id=email.id,
                    actor=actor,
                    reporting_quarter=period,
                    distributor_id=distributor_id,
                    mark_duplicate_as_error=False,
                    confidence_breakdown=(preview.get("confidence") or {}).get("breakdown"),
                    workbook_meta={
                        "sheet_name": preview.get("sheet_name"),
                        "workbook_name": att.file_name,
                        "monthly_pivot": preview.get("monthly_pivot"),
                        "fiscal_year_start": preview.get("fiscal_year_start") or fiscal_year_start,
                    },
                    allow_existing_file=bool(replace_existing),
                )
            except ValidationAppError as exc:
                if exc.message != DUPLICATE_SUBMISSION_MESSAGE or replace_existing or total_inserted:
                    raise
                existing = self._count_period_scope(
                    distributor_id, period, segment, location
                ) or len(parsed)
                blocked = self._combine_duplicate_review(
                    company,
                    [
                        self._review_hit(
                            company=company,
                            period=period,
                            existing_rows=existing,
                            new_rows=len(parsed),
                        )
                    ],
                )
                return 0, True, None, [], 0, blocked
            if replace_existing:
                self._recount_report_rows(report)
            total_inserted += inserted
            any_dup = any_dup or was_dup
            last_report = report
            quarters_imported.append(period)
        return total_inserted, any_dup, last_report, quarters_imported, len(quarters_imported), None

    def import_approved(
        self,
        *,
        email_id: int,
        distributor_id: Optional[int] = None,
        reporting_quarter: Optional[str] = None,
        actor: str,
        mapping: Optional[Any] = None,
        rows: Optional[List[Dict[str, Any]]] = None,
        fiscal_year_start: Optional[int] = None,
        replace_existing: bool = False,
    ) -> Dict[str, Any]:
        """Persist approved ERP rows after accuracy + mapping review.

        Processes up to ``MAX_EXCEL_ATTACHMENTS_PER_EMAIL`` Excel files on the
        email. Manual ``mapping`` / client ``rows`` apply only to the primary
        (first) workbook; remaining workbooks are re-parsed server-side.
        """
        from app.services.email_subject_service import EmailSubjectService

        email = self.emails.get_or_raise(email_id)
        EmailSubjectService(self.db).require_valid_subject(email)
        attachments = self._list_excel_attachments(email)
        if not attachments:
            raise ValidationAppError("No Excel attachment found for this email")

        subject_dist = self.resolve_distributor_from_subject(email)
        resolved_id = distributor_id or (subject_dist["id"] if subject_dist else None)
        if resolved_id is None:
            raise ValidationAppError(
                "Distributor could not be resolved from email subject. "
                "Use format: Distributor | Location | Segment"
            )

        dist = self.distributors.get_or_raise(resolved_id)
        if not dist.is_active or dist.is_deleted:
            raise ValidationAppError("Distributor is inactive")

        company = (dist.company or dist.name or "").strip()
        from app.constants.business_segments import normalize_business_segment

        segment = normalize_business_segment(email.parsed_segment)
        location = (email.parsed_location or "").strip()
        from app.utils.distributor_location import apply_submitted_location

        if apply_submitted_location(dist, location):
            self.db.flush()
        quarter = (reporting_quarter or "").strip()
        total_inserted = 0
        any_dup = False
        last_report = None
        quarters_imported: List[str] = []
        reports_created = 0
        workbooks_imported: List[str] = []
        workbook_skips: List[Dict[str, Any]] = []
        qualities: List[float] = []
        merged_rows: List[Dict[str, Any]] = []
        primary_att = None
        primary_preview: Dict[str, Any] = {}
        from app.utils.email_subject_parser import parse_email_subject

        subject_meta = parse_email_subject(email.subject)
        subject_month = str(subject_meta.get("source_month") or "").strip()
        source_unit = str(subject_meta.get("unit") or email.parsed_unit or "MT").strip() or "MT"
        subject_period = (email.detected_quarter or reporting_quarter or "").strip()

        preferred_parser, known_fingerprint = self._preferred_parser_pair(email)
        known_profiles = self._known_profiles(email)
        if mapping:
            preferred_parser = None
            known_profiles = None
        for idx, att in enumerate(attachments):
            path = Path(att.file_path or "")
            if not path.is_file():
                workbook_skips.append(
                    {"workbook": att.file_name, "reason": "file missing on disk"}
                )
                continue

            try:
                # Mapping / client rows only for the primary workbook (Preview remap).
                if idx == 0 and mapping:
                    preview = self._preview_with_override(
                        path,
                        mapping,
                        fiscal_year_start=fiscal_year_start,
                        reporting_quarter=quarter or None,
                    )
                    use_rows = preview.get("rows") or rows or []
                elif idx == 0 and rows and len(attachments) == 1:
                    # Single-file Approve with precomputed rows (no remap)
                    preview = self.parser.preview(
                        path,
                        fiscal_year_start=fiscal_year_start,
                        reporting_quarter=quarter or None,
                        distributor_label=email.parsed_distributor or "",
                        subject=email.subject,
                        preferred_parser=preferred_parser,
                        known_fingerprint=known_fingerprint,
                        known_profiles=known_profiles,
                    )
                    use_rows = rows
                else:
                    # Multi-file or subsequent attachments: always re-parse
                    preview = self.parser.preview(
                        path,
                        fiscal_year_start=fiscal_year_start,
                        reporting_quarter=quarter or None,
                        distributor_label=email.parsed_distributor or "",
                        subject=email.subject,
                        preferred_parser=preferred_parser,
                        known_fingerprint=known_fingerprint,
                        known_profiles=known_profiles,
                    )
                    use_rows = preview.get("rows") or []
                if not quarter:
                    quarter = self._resolve_reporting_quarter(
                        email, preview, override=reporting_quarter
                    )
                    if not email.detected_quarter:
                        email.detected_quarter = quarter
                        self.db.flush()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ERP import parse failed | email_id={} | file={} | err={}",
                    email_id,
                    att.file_name,
                    exc,
                )
                workbook_skips.append(
                    {"workbook": att.file_name, "reason": f"parse failed: {exc}"}
                )
                continue

            overall = float((preview.get("confidence") or {}).get("overall") or 0)
            if overall < MIN_IMPORT_ACCURACY:
                workbook_skips.append(
                    {
                        "workbook": att.file_name,
                        "reason": f"accuracy {round(overall)}% < {int(MIN_IMPORT_ACCURACY)}%",
                    }
                )
                continue
            if not use_rows:
                workbook_skips.append(
                    {"workbook": att.file_name, "reason": "no rows extracted"}
                )
                continue

            if subject_period or subject_month or subject_meta.get("allowed_quarters"):
                from app.erp_parser.documents.row_quarters import assign_row_periods

                handled, review_notes = assign_row_periods(use_rows, subject_meta)
                if review_notes:
                    logger.warning(
                        "Quarter outside subject range | email_id={} | count={}",
                        email_id,
                        len(review_notes),
                    )
                if not handled:
                    for row in use_rows:
                        if not isinstance(row, dict):
                            continue
                        if subject_period:
                            row["period"] = subject_period
                            row["reporting_quarter"] = subject_period
                        if subject_month and not str(row.get("source_month") or "").strip():
                            row["source_month"] = subject_month
                use_rows = [row for row in use_rows if isinstance(row, dict) and not row.get("human_review")]
            merged_rows.extend(use_rows)
            workbooks_imported.append(att.file_name or f"attachment-{att.id}")
            qualities.append(overall)
            if primary_att is None:
                primary_att = att
                primary_preview = preview

        if not workbooks_imported or primary_att is None:
            detail = workbook_skips or [{"reason": "no importable Excel attachments"}]
            raise ValidationAppError(
                "No Excel attachments could be imported for this email.",
                details={"skips": detail},
            )

        try:
            inserted, was_dup, last_report, quarters_imported, reports_created, review = (
                self._persist_preview_rows(
                    email=email,
                    att=primary_att,
                    preview=primary_preview,
                    use_rows=merged_rows,
                    distributor_id=resolved_id,
                    company=company,
                    quarter=subject_period or quarter,
                    segment=segment,
                    location=location,
                    source_unit=source_unit,
                    actor=actor,
                    fiscal_year_start=fiscal_year_start,
                    overall=min(qualities) if qualities else 0.0,
                    replace_existing=replace_existing,
                )
            )
        except ValidationAppError as exc:
            if exc.message == DUPLICATE_SUBMISSION_MESSAGE:
                raise
            raise ValidationAppError(
                "Merged Excel submission could not be imported.",
                details={"reason": str(exc.message), "skips": workbook_skips},
            ) from exc

        if review:
            period_label = (
                review["periods"][0]
                if review.get("periods")
                else (subject_period or quarter)
            )
            return {
                "report_id": 0,
                "records_inserted": 0,
                "duplicate": True,
                "requires_review": True,
                "duplicate_review": review,
                "quality_score": int(round(min(qualities) if qualities else 0.0)),
                "distributor_id": resolved_id,
                "reporting_quarter": period_label,
                "workbook_name": (
                    workbooks_imported[0]
                    if len(workbooks_imported) == 1
                    else f"{len(workbooks_imported)} workbooks"
                ),
                "workbooks_imported": [],
                "workbook_skips": workbook_skips,
                "reports_created": 0,
                "quarters_imported": [],
            }

        total_inserted = inserted
        any_dup = was_dup
        overall_quality = min(qualities) if qualities else 0.0
        email.process_status = EmailProcessStatus.INSERTED.value
        email.confidence_score = int(round(overall_quality))
        if workbook_skips:
            email.error_message = (
                f"Imported {len(workbooks_imported)} workbook(s); "
                f"skipped {len(workbook_skips)}: "
                + "; ".join(
                    f"{s.get('workbook')}: {s.get('reason')}" for s in workbook_skips[:5]
                )
            )
        else:
            email.error_message = None
        self.db.flush()

        unique_quarters = list(dict.fromkeys(quarters_imported))
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action="Imported Report",
                details=(
                    f"ERP Report Imported | email_id={email_id} | "
                    f"distributor={company} | segment={segment} | location={location} | "
                    f"quarters={unique_quarters} | "
                    f"workbooks={workbooks_imported} | rows={total_inserted} | "
                    f"skipped={len(workbook_skips)}"
                ),
                entity_type="report",
                entity_id=str(last_report.id if last_report else ""),
                module="Email Extraction",
                status="Success",
                report_name=", ".join(workbooks_imported[:3]),
                extra_metadata={
                    "email_id": email_id,
                    "distributor_id": resolved_id,
                    "distributor": company,
                    "segment": segment,
                    "location": location,
                    "quarters_imported": unique_quarters,
                    "workbooks": workbooks_imported,
                    "workbook_skips": workbook_skips,
                    "row_count": total_inserted,
                    "duplicate": any_dup,
                },
            )
        )

        return {
            "report_id": last_report.id if last_report else 0,
            "records_inserted": total_inserted,
            "duplicate": any_dup,
            "quality_score": int(round(overall_quality)),
            "distributor_id": resolved_id,
            "reporting_quarter": (
                ", ".join(unique_quarters)
                if len(unique_quarters) > 1
                else (unique_quarters[0] if unique_quarters else quarter)
            ),
            "workbook_name": (
                workbooks_imported[0]
                if len(workbooks_imported) == 1
                else f"{len(workbooks_imported)} workbooks"
            ),
            "workbooks_imported": workbooks_imported,
            "workbook_skips": workbook_skips,
            "reports_created": reports_created,
            "quarters_imported": unique_quarters,
        }

    def skip_email(self, email_id: int, *, actor: str) -> Dict[str, Any]:
        email = self.emails.get_or_raise(email_id)
        email.process_status = EmailProcessStatus.SKIPPED.value
        self.db.flush()
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPDATED,
                details=f"ERP Email Skipped | email_id={email_id} | subject={email.subject}",
                entity_type="email",
                entity_id=str(email_id),
                module="Email Extraction",
                status="Success",
            )
        )
        return {"email_id": email_id, "status": "skipped"}
