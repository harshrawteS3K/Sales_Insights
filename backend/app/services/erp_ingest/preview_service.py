"""Email preview and mapping override preview."""

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
from app.utils.quantity import format_quantity, kg_to_mt_display, parse_quantity

class PreviewMixin:
    def _log_email_job(self, email: Any, attachment_summary: List[Dict[str, Any]], merged_rows: List[Dict[str, Any]]) -> None:
        parsed = [item for item in attachment_summary if item.get("status") == "Parsed"]
        if not parsed:
            return
        dominant = max(parsed, key=lambda item: int(item.get("row_count") or 0))
        confidence_values = [float(item.get("confidence") or 0) for item in parsed]
        confidence = min(confidence_values) if confidence_values else 0
        duration = sum(float(item.get("duration_sec") or 0) for item in parsed)
        llm_used = any(item.get("llm_used") for item in parsed)
        tokens = sum(int(item.get("llm_tokens") or 0) for item in parsed if item.get("llm_used"))
        reasons = [str(item.get("llm_reason")) for item in parsed if item.get("llm_used") and item.get("llm_reason")]
        email_name = email.parsed_distributor or email.subject or "Email"
        document_name = dominant.get("attachment_name") or ""
        document_type = dominant.get("document_type") or ""
        from app.erp_parser.documents.row_quarters import quarter_split

        split = quarter_split(merged_rows)
        split_lines = "\n".join(f"{name} : {count}" for name, count in sorted(split.items())) or "—"
        parser_name = dominant.get("parser_used") or ""
        if str(document_type).upper() == "PDF" and "stock register" not in str(parser_name).lower():
            parser_name = "PDF Adapter"
        logger.info(
            "AI Job\n\nDistributor : {}\n\nDocument : {}\n\nType : {}\n\nLayout : {}\n\nParser : {}\n\nRows Parsed : {}\n\nQuarter Split :\n{}\n\nConfidence : {}\n\nLLM Used : {}\n\nDuration : {:.2f} sec",
            email_name,
            document_name,
            document_type,
            dominant.get("layout") or "",
            parser_name,
            len(merged_rows),
            split_lines,
            int(round(confidence)),
            "Yes" if llm_used else "No",
            duration,
        )
        if llm_used:
            from app.llm.model_registry import display_name_for

            logger.info(
                "LLM Structure Assist\n\nReason : {}\n\nModel : {}\n\nInput Tokens : {}\nOutput Tokens : {}\nReturned Layout : {}",
                reasons[0] if reasons else "Unknown Layout",
                dominant.get("llm_model") or display_name_for(None),
                tokens,
                0,
                dominant.get("layout") or "",
            )

    def preview_email(
        self,
        email_id: int,
        *,
        actor: str = "system",
        mapping_override: Optional[Any] = None,
        fiscal_year_start: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Parse every Excel on the email into one merged preview (no import)."""
        from app.services.email_subject_service import EmailSubjectService

        email = self.emails.get_or_raise(email_id)
        EmailSubjectService(self.db).apply_to_email(email, actor=actor, skip_if_valid=True)
        if not email.subject_valid:
            raise ValidationAppError(
                email.error_message
                or "Invalid email subject. Expected format: Distributor | Location | Segment",
                details={"email_id": email_id, "subject": email.subject},
            )
        attachments = self._list_excel_attachments(email)
        if not attachments:
            raise ValidationAppError("No Excel, PDF, or Word attachment found for this email")

        subject_period = (email.detected_quarter or "").strip()
        from app.erp_parser.documents.row_quarters import assign_row_periods
        from app.utils.email_subject_parser import try_parse_email_subject

        subject_meta = try_parse_email_subject(email.subject) or {}
        preferred_parser, known_fingerprint = self._preferred_parser_pair(email)
        known_profiles = self._known_profiles(email)
        merged_rows: List[Dict[str, Any]] = []
        attachment_summary: List[Dict[str, str]] = []
        preview: Optional[Dict[str, Any]] = None
        confidences: List[float] = []
        primary_name = attachments[0].file_name

        for idx, att in enumerate(attachments):
            file_name = att.file_name or f"attachment-{att.id}"
            product_name = Path(file_name).stem
            path = Path(att.file_path or "")
            if not path.is_file():
                attachment_summary.append(
                    {
                        "attachment_name": file_name,
                        "product_name": product_name,
                        "status": "Failed",
                    }
                )
                continue
            try:
                if idx == 0 and mapping_override:
                    one = self._preview_with_override(
                        path,
                        mapping_override,
                        fiscal_year_start=fiscal_year_start,
                        reporting_quarter=subject_period or None,
                    )
                else:
                    one = self.parser.preview(
                        path,
                        fiscal_year_start=fiscal_year_start,
                        reporting_quarter=subject_period or None,
                        distributor_label=email.parsed_distributor or "",
                        subject=email.subject,
                        preferred_parser=preferred_parser,
                        known_fingerprint=known_fingerprint,
                        known_profiles=known_profiles,
                    )
                    if idx == 0:
                        one["available_columns"] = self._available_columns(
                            path, one.get("sheet_name")
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ERP preview parse failed | email_id={} | file={} | err={}",
                    email_id,
                    file_name,
                    exc,
                )
                message = str(exc)
                status = "Human Review" if "Human review" in message or "Could not map" in message else "Failed"
                attachment_summary.append(
                    {
                        "attachment_name": file_name,
                        "product_name": product_name,
                        "status": status,
                        "document_type": "",
                    }
                )
                continue

            rows = list(one.get("rows") or [])
            distinct_products = []
            for row in rows:
                name = str((row or {}).get("product") or "").strip()
                if name and name not in distinct_products:
                    distinct_products.append(name)
            if len(distinct_products) == 1:
                product_name = distinct_products[0]
            if subject_period or subject_meta.get("allowed_quarters"):
                handled, review_notes = assign_row_periods(rows, subject_meta)
                if not handled and subject_period:
                    for row in rows:
                        row["period"] = subject_period
                        row["reporting_quarter"] = subject_period
                elif review_notes:
                    logger.warning(
                        "Quarter outside subject range | file={} | count={}",
                        file_name,
                        len(review_notes),
                    )
            job = (one.get("confidence") or {}).get("breakdown") or {}
            attachment_summary.append(
                {
                    "attachment_name": file_name,
                    "product_name": product_name,
                    "status": "Parsed",
                    "parser_used": str(one.get("parser_used") or ""),
                    "parser_version": str(job.get("parser_version") or ""),
                    "layout": str(job.get("layout_name") or job.get("layout") or ""),
                    "fingerprint": str(job.get("fingerprint") or ""),
                    "terminal_state": str(job.get("terminal_state") or ""),
                    "confidence": float(one.get("orchestrator_confidence") or 0),
                    "sheet_count": int(one.get("sheet_count") or 0),
                    "llm_used": bool(one.get("llm_used")),
                    "llm_tokens": int(one.get("llm_tokens") or 0),
                    "llm_reason": str(one.get("llm_reason") or ""),
                    "llm_model": str(job.get("llm_model") or ""),
                    "row_count": len(rows),
                    "duration_sec": float(one.get("duration_sec") or 0),
                    "document_type": str(job.get("document_type") or ""),
                }
            )
            merged_rows.extend(rows)
            confidences.append(float((one.get("confidence") or {}).get("overall") or 0))
            if not mapping_override:
                self._remember_parser(email, one)
            if preview is None:
                preview = one
                primary_name = file_name

        if preview is None:
            raise ValidationAppError(
                "No Excel attachments could be parsed for this email.",
                details={"attachment_summary": attachment_summary},
            )

        for row in merged_rows:
            if not isinstance(row, dict):
                continue
            row["sales_quantity_mt"] = kg_to_mt_display(row.get("sales_quantity"))
            row["unit"] = "MT"
        preview["rows"] = merged_rows
        preview["row_count"] = len(merged_rows)
        if confidences and preview.get("confidence"):
            preview["confidence"]["overall"] = min(confidences)
            preview["accuracy"] = min(confidences)
        preview["attachment_summary"] = attachment_summary
        self._log_email_job(email, attachment_summary, merged_rows)

        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.PROCESSED,
                details=(
                    f"ERP Workbook Parsed | email_id={email_id} | "
                    f"attachments={len(attachment_summary)} | rows={len(merged_rows)}"
                ),
                entity_type="email",
                entity_id=str(email_id),
                module="Email Extraction",
                status="Success",
                extra_metadata={
                    "workbook": primary_name,
                    "row_count": len(merged_rows),
                    "attachment_summary": attachment_summary,
                },
            )
        )

        att = attachments[0]
        subject_match = self.resolve_distributor_from_subject(email)
        sender_matches = self.resolve_distributors_for_sender(email.sender_email)
        matches = [subject_match] if subject_match else sender_matches
        all_excels = attachments
        detected_q = (subject_period or preview.get("detected_quarter") or "").strip()
        # Subject period wins; only fill from workbook when empty
        if detected_q and not (email.detected_quarter or "").strip():
            email.detected_quarter = detected_q
            self.db.flush()
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action="Quarter Detected",
                    details=(
                        f"Quarter detected for email_id={email_id} | quarter={detected_q} | "
                        f"confidence={preview.get('quarter_confidence')}"
                    ),
                    entity_type="email",
                    entity_id=str(email_id),
                    module="Email Extraction",
                    status="Success",
                    extra_metadata={
                        "segment": email.parsed_segment,
                        "reporting_quarter": detected_q,
                        "confidence": preview.get("quarter_confidence"),
                    },
                )
            )
        elif (email.detected_quarter or "").strip():
            preview["detected_quarter"] = email.detected_quarter
        preview["email_id"] = email.id
        preview["workbook_name"] = att.file_name
        preview["subject"] = email.subject
        preview["sender_email"] = email.sender_email
        preview["sender_name"] = email.sender_name
        preview["distributor_matches"] = matches
        preview["all_distributors"] = self.list_active_distributors()
        preview["distributor_id"] = matches[0]["id"] if len(matches) == 1 else None
        preview["distributor_unknown"] = len(matches) == 0
        preview["subject_valid"] = bool(email.subject_valid)
        preview["parsed_distributor"] = email.parsed_distributor
        preview["parsed_location"] = email.parsed_location
        preview["parsed_segment"] = email.parsed_segment
        preview["detected_quarter"] = detected_q or preview.get("detected_quarter")
        preview["import_allowed"] = (
            float((preview.get("confidence") or {}).get("overall") or 0) >= MIN_IMPORT_ACCURACY
            and bool(email.subject_valid)
            and preview["distributor_id"] is not None
            and bool(preview.get("detected_quarter") or preview.get("monthly_pivot"))
        )
        preview["attachment_count"] = len(all_excels)
        preview["attachment_names"] = [a.file_name for a in all_excels]
        preview["attachments_capped"] = len(
            [a for a in (email.attachments or []) if self._is_excel_att(a)]
        ) > MAX_EXCEL_ATTACHMENTS_PER_EMAIL
        if preview.get("distributor_id"):
            from collections import Counter

            period_counts: Counter[str] = Counter()
            for row in merged_rows:
                period = str(
                    (row or {}).get("period")
                    or (row or {}).get("reporting_quarter")
                    or preview.get("detected_quarter")
                    or ""
                ).strip()
                if period:
                    period_counts[period] += 1
            company_name = str(email.parsed_distributor or "").strip()
            match = matches[0] if len(matches) == 1 else None
            if match:
                company_name = str(match.get("company") or company_name).strip()
            hits = self._duplicate_hits_for_periods(
                distributor_id=int(preview["distributor_id"]),
                company=company_name,
                segment=str(email.parsed_segment or ""),
                location=str(email.parsed_location or ""),
                counts_by_period=dict(period_counts),
            )
            preview["duplicate_review"] = self._combine_duplicate_review(
                company_name, hits
            )
        else:
            preview["duplicate_review"] = None

        if email.process_status not in {
            EmailProcessStatus.INSERTED.value,
            EmailProcessStatus.MARKED_READ.value,
        }:
            email.process_status = EmailProcessStatus.PARSED.value
            conf = (preview.get("confidence") or {}).get("overall")
            if conf is not None:
                email.confidence_score = int(round(float(conf)))
            src = preview.get("mapping_source")
            if src:
                email.mapping_source = str(src)
            email.error_message = None
            self.db.flush()

        return preview

    def _preview_with_override(
        self,
        path: Path,
        mapping_override: Any,
        *,
        fiscal_year_start: Optional[int] = None,
        reporting_quarter: Optional[str] = None,
    ) -> Dict[str, Any]:
        override = self._coerce_override(mapping_override)
        sheet_name, sheet_score = detect_best_sheet(path)
        matrix = read_sheet_matrix(path, sheet_name)
        header_info = detect_header_row(matrix)
        header_idx = header_info["header_row_index"]
        header_row = list(matrix[header_idx]) if matrix else []
        auto = header_info["mapping"]
        positions = self._resolve_override_positions(header_row, override)
        month_meta = list(auto.get("month_column_meta") or [])
        qty_cols = list(auto.get("quantity_columns") or [])
        if qty_cols and positions.get("quantity") is None:
            positions["quantity"] = qty_cols[0]

        if (
            positions.get("customer") is None
            or positions.get("product") is None
            or (positions.get("quantity") is None and not qty_cols)
        ):
            raise ValidationAppError(
                "Mapping must include Customer Name, Product, and Sales Quantity columns."
            )

        extracted = extract_rows(
            matrix,
            header_row_index=header_idx,
            positions=positions,
            quantity_columns=qty_cols or None,
            month_column_meta=month_meta or None,
            fiscal_year_start=fiscal_year_start,
            reporting_quarter=reporting_quarter,
        )
        raw_rows = extracted["rows"]
        if not raw_rows:
            raise ExcelProcessingError("No valid rows with the selected mapping")

        field_conf = {
            "customer": 100.0,
            "product": 100.0,
            "quantity": 95.0 if extracted.get("monthly_pivot") else 100.0,
        }
        confidence = compute_erp_confidence(
            field_confidences=field_conf,
            sheet_score=sheet_score,
            extracted_rows=len(raw_rows),
            quantity_ok=extracted["quantity_ok"],
            quantity_fail=extracted["quantity_fail"],
            skipped_invalid=extracted["skipped_invalid"],
        )

        mapping_list = []
        for field in ("customer", "product", "quantity"):
            col = positions[field]
            original = (
                str(header_row[col]).strip()
                if col is not None and col < len(header_row) and header_row[col] is not None
                else ("Monthly columns → quarterly totals" if field == "quantity" and qty_cols else None)
            )
            mapping_list.append(
                {
                    "field": field,
                    "original": original,
                    "mapped": FIELD_DISPLAY[field],
                    "confidence": field_conf[field],
                    "method": "monthly_sum" if field == "quantity" and extracted.get("monthly_pivot") else "manual",
                    "column": (col + 1) if col is not None else None,
                }
            )

        available_columns = []
        for i, h in enumerate(header_row):
            text = str(h).strip() if h is not None else ""
            if text:
                available_columns.append({"index": i, "header": text, "column": i + 1})

        return {
            "sheet_name": sheet_name,
            "sheet_score": sheet_score,
            "header_row": header_idx + 1,
            "confidence": {
                "overall": confidence["overall_confidence"],
                "accuracy": confidence["overall_confidence"],
                "customer": confidence["customer_confidence"],
                "product": confidence["product_confidence"],
                "quantity": confidence["quantity_confidence"],
                "band": confidence["band"],
                "breakdown": {
                    **confidence,
                    "fiscal_year_start": extracted.get("fiscal_year_start"),
                    "monthly_pivot": extracted.get("monthly_pivot"),
                },
            },
            "accuracy": confidence["overall_confidence"],
            "mapping": mapping_list,
            "column_positions": {
                f: (positions[f] + 1 if positions[f] is not None else None)
                for f in ("customer", "product", "quantity")
            },
            "rows": [
                {
                    "customer_name": r["customer_name"],
                    "product": r["product"],
                    "sales_quantity": float(r["sales_quantity"]),
                    **(
                        {"period": r["period"], "reporting_quarter": r["period"]}
                        if r.get("period")
                        else {}
                    ),
                }
                for r in raw_rows
            ],
            "row_count": len(raw_rows),
            "candidate_sheets": [sheet_name],
            "errors": extracted.get("errors") or [],
            "available_columns": available_columns,
            "monthly_pivot": bool(extracted.get("monthly_pivot")),
            "fiscal_year_start": extracted.get("fiscal_year_start"),
            "mapping_source": "manual",
        }

