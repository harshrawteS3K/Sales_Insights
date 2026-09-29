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
        row_decisions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Persist rows. Modified rows wait for a reviewer decision and write nothing."""
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
        if not replace_existing:
            return self._persist_incremental(
                email=email,
                att=att,
                preview=preview,
                use_rows=use_rows,
                by_period=by_period,
                distributor_id=distributor_id,
                company=company,
                segment=segment,
                location=location,
                actor=actor,
                fiscal_year_start=fiscal_year_start,
                overall=overall,
                row_decisions=row_decisions,
                source_unit=source_unit,
            )
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
                return {
                    "inserted": 0,
                    "updated": 0,
                    "exact": 0,
                    "was_dup": True,
                    "report": None,
                    "quarters": [],
                    "reports_created": 0,
                    "review": blocked,
                    "plan": None,
                    "outcome": "review",
                }
            if replace_existing:
                self._recount_report_rows(report)
            total_inserted += inserted
            any_dup = any_dup or was_dup
            last_report = report
            quarters_imported.append(period)
        return {
            "inserted": total_inserted,
            "updated": 0,
            "exact": 0,
            "was_dup": any_dup,
            "report": last_report,
            "quarters": quarters_imported,
            "reports_created": len(quarters_imported),
            "review": None,
            "plan": None,
            "outcome": "imported",
        }

    def _persist_incremental(
        self,
        *,
        email: Any,
        att: Any,
        preview: Dict[str, Any],
        use_rows: List[Dict[str, Any]],
        by_period: Dict[str, List[ParsedSalesRow]],
        distributor_id: int,
        company: str,
        segment: str,
        location: str,
        actor: str,
        fiscal_year_start: Optional[int],
        overall: float,
        row_decisions: Optional[List[Dict[str, Any]]],
        source_unit: str = "KG",
    ) -> Dict[str, Any]:
        """Insert new rows, skip exact copies, and apply reviewer choices for changes."""
        from decimal import Decimal

        from app.models.sales_record import SalesRecord
        from app.services.incremental_upload import (
            ADD,
            KEEP,
            analyse_rows,
            decision_map,
            load_existing,
            needs_review,
            public_plan,
            rows_for_insert,
            rows_for_replace,
        )
        from app.utils.quantity import format_quantity

        existing = load_existing(self.db, distributor_id)
        plan = analyse_rows(use_rows, existing)
        shown = public_plan(plan)
        if needs_review(plan, row_decisions):
            shown_review = {
                "detected": True,
                "message": shown["recommendation"],
                "distributor": company,
                "financial_year": "",
                "quarter": "",
                "existing_rows": shown["exact_count"] + shown["modified_count"],
                "new_rows": shown["new_count"],
                "periods": [],
            }
            return {
                "inserted": 0,
                "updated": 0,
                "exact": shown["exact_count"],
                "was_dup": shown["exact_count"] > 0,
                "report": None,
                "quarters": [],
                "reports_created": 0,
                "review": shown_review,
                "plan": shown,
                "outcome": "review",
            }

        chosen = decision_map(row_decisions)
        replacements = rows_for_replace(plan, row_decisions)
        updated = 0
        for change in replacements:
            record = self.db.get(SalesRecord, int(change["existing_id"]))
            if record is None or record.is_deleted:
                continue
            record.quantity = Decimal(str(change["incoming_qty"]))
            record.quantity_display = format_quantity(record.quantity)
            record.row_hash = build_sales_row_hash(
                company,
                record.customer_name,
                record.segment or segment,
                record.product,
                record.quantity,
                record.period or change.get("date") or "",
                record.source_month or "",
            )
            updated += 1
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action="Replace",
                    details=(
                        f"Modified row replaced | distributor={company} | "
                        f"customer={change['customer']} | product={change['product']} | "
                        f"date={change['date']} | existing={change['existing_qty']} | "
                        f"incoming={change['incoming_qty']}"
                    ),
                    entity_type="sales_record",
                    entity_id=str(change["existing_id"]),
                    module="Email Extraction",
                    status="Success",
                )
            )
        for item in plan.get("rows") or []:
            action = chosen.get(int(item["row_index"]))
            if item["kind"] == "modified" and action == KEEP:
                self.audit.log(
                    AuditTrailCreate(
                        user_name=actor,
                        action="Keep Existing",
                        details=(
                            f"distributor={company} | customer={item['customer']} | "
                            f"product={item['product']} | date={item['date']} | "
                            f"qty={item['incoming_qty']}"
                        ),
                        entity_type="sales_record",
                        entity_id=str(item.get("existing_id") or ""),
                        module="Email Extraction",
                        status="Info",
                    )
                )
        if updated:
            self.db.flush()

        insert_rows = rows_for_insert(use_rows, plan, row_decisions)
        _ = by_period
        if not insert_rows and updated == 0:
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action="Duplicate Upload",
                    details=(
                        f"Distributor: {company} | Rows Analysed: {shown['analysed']} | "
                        f"Inserted: 0 | Duplicates: {shown['exact_count']} | "
                        f"Modified: {shown['modified_count']} | Reviewer: {actor}"
                    ),
                    entity_type="email",
                    entity_id=str(email.id),
                    module="Email Extraction",
                    status="Info",
                )
            )
            return {
                "inserted": 0,
                "updated": 0,
                "exact": shown["exact_count"],
                "was_dup": True,
                "report": None,
                "quarters": [],
                "reports_created": 0,
                "review": None,
                "plan": shown,
                "outcome": "duplicate_upload",
            }

        fresh_periods = self._rows_by_period(
            insert_rows,
            company=company,
            quarter="",
            segment=segment,
            location=location,
            source_unit=source_unit or "KG",
        ) if insert_rows else {}
        total_inserted = 0
        last_report = None
        quarters_imported: List[str] = []
        path = Path(att.file_path)
        for period, parsed in sorted(fresh_periods.items()):
            report, inserted, _was_dup, _quality = self.reports.persist_approved_rows(
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
                allow_existing_file=True,
            )
            total_inserted += inserted
            last_report = report
            quarters_imported.append(period)
        kept = sum(1 for item in plan.get("rows") or [] if chosen.get(int(item["row_index"])) == KEEP)
        added = sum(1 for item in plan.get("rows") or [] if chosen.get(int(item["row_index"])) == ADD)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action="Incremental Import",
                details=(
                    f"Distributor: {company} | Rows Analysed: {shown['analysed']} | "
                    f"Inserted: {total_inserted} | Duplicates: {shown['exact_count']} | "
                    f"Modified: {shown['modified_count']} | Reviewer: {actor} | "
                    f"Replace ({updated}) | Keep ({kept}) | Add ({added})"
                ),
                entity_type="email",
                entity_id=str(email.id),
                module="Email Extraction",
                status="Success",
            )
        )
        return {
            "inserted": total_inserted,
            "updated": updated,
            "exact": shown["exact_count"],
            "was_dup": shown["exact_count"] > 0,
            "report": last_report,
            "quarters": quarters_imported,
            "reports_created": len(quarters_imported),
            "review": None,
            "plan": shown,
            "outcome": "imported",
        }

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
        row_decisions: Optional[List[Dict[str, Any]]] = None,
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
            saved = self._persist_preview_rows(
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
                row_decisions=row_decisions,
            )
            inserted = int(saved.get("inserted") or 0)
            was_dup = bool(saved.get("was_dup"))
            last_report = saved.get("report")
            quarters_imported = list(saved.get("quarters") or [])
            reports_created = int(saved.get("reports_created") or 0)
            review = saved.get("review")
            outcome = str(saved.get("outcome") or "imported")
            plan = saved.get("plan")
        except ValidationAppError as exc:
            if exc.message == DUPLICATE_SUBMISSION_MESSAGE:
                raise
            raise ValidationAppError(
                "Merged Excel submission could not be imported.",
                details={"reason": str(exc.message), "skips": workbook_skips},
            ) from exc

        if outcome == "duplicate_upload":
            email.process_status = EmailProcessStatus.DUPLICATE_UPLOAD.value
            email.error_message = "Duplicate Upload. No records inserted."
            self.db.flush()
            return {
                "report_id": 0,
                "records_inserted": 0,
                "records_updated": 0,
                "duplicates_skipped": int((plan or {}).get("exact_count") or 0),
                "duplicate": True,
                "duplicate_upload": True,
                "requires_review": False,
                "duplicate_review": None,
                "incremental_analysis": plan,
                "quality_score": int(round(min(qualities) if qualities else 0.0)),
                "distributor_id": resolved_id,
                "reporting_quarter": subject_period or quarter,
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

        if review or outcome == "review":
            if email.process_status not in {
                EmailProcessStatus.INSERTED.value,
                EmailProcessStatus.MARKED_READ.value,
            }:
                email.process_status = EmailProcessStatus.INCREMENTAL_REVIEW.value
                email.error_message = None
                self.db.flush()
            period_label = (
                (review or {}).get("periods") or [None]
            )[0] or (subject_period or quarter)
            return {
                "report_id": 0,
                "records_inserted": 0,
                "records_updated": 0,
                "duplicates_skipped": int((plan or {}).get("exact_count") or 0),
                "duplicate": True,
                "duplicate_upload": False,
                "requires_review": True,
                "duplicate_review": review,
                "incremental_analysis": plan,
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
            "records_updated": int(saved.get("updated") or 0),
            "duplicates_skipped": int(saved.get("exact") or 0),
            "duplicate": any_dup,
            "duplicate_upload": False,
            "incremental_analysis": plan,
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
