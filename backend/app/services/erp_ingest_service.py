"""ERP email preview + approved import workflow."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction, EmailProcessStatus, ReportSource
from app.erp_parser import ERPParserService
from app.erp_parser.confidence import compute_erp_confidence
from app.erp_parser.header_detector import detect_header_row
from app.erp_parser.header_mapper import FIELD_DISPLAY, normalize_header_text
from app.erp_parser.row_extractor import extract_rows
from app.erp_parser.sheet_detector import detect_best_sheet
from app.erp_parser.workbook_detector import read_sheet_matrix
from app.exceptions import ExcelProcessingError, ValidationAppError
from app.repositories.distributor_repository import DistributorRepository
from app.repositories.email_repository import EmailMessageRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.sales_record import ParsedSalesRow
from app.services.audit_service import AuditService
from app.services.report_service import ReportService
from app.utils.hashing import build_sales_row_hash
from app.utils.quantity import parse_quantity

logger = get_logger(__name__)

# Cap Excel workbooks processed per email (download / score / import).
MAX_EXCEL_ATTACHMENTS_PER_EMAIL = 5
MIN_IMPORT_ACCURACY = 75.0

_FIELD_ALIASES = {
    "customer": "customer",
    "customer name": "customer",
    "customer_name": "customer",
    "product": "product",
    "sales quantity": "quantity",
    "sales_quantity": "quantity",
    "quantity": "quantity",
    "ignored": "ignored",
    "ignore": "ignored",
}


def _normalize_mapped_field(value: str) -> str:
    key = normalize_header_text(value)
    return _FIELD_ALIASES.get(key, key)


class ERPIngestService:
    """Preview ERP attachments and import after admin approval."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.emails = EmailMessageRepository(db)
        self.distributors = DistributorRepository(db)
        self.parser = ERPParserService()
        self.reports = ReportService(db)
        self.audit = AuditService(db)

    def resolve_distributor_from_subject(self, email: Any) -> Optional[Dict[str, Any]]:
        """Resolve distributor from parsed email subject (business identity)."""
        if not getattr(email, "subject_valid", False) or not email.parsed_distributor:
            return None
        dist = self.distributors.get_or_create_by_company(
            email.parsed_distributor,
            representative_name=email.parsed_distributor,
        )
        if not dist.is_active or dist.is_deleted:
            return None
        return {
            "id": dist.id,
            "company": dist.company or dist.name,
            "name": dist.name,
            "email": dist.email,
            "match": "subject",
        }

    def resolve_distributors_for_sender(self, sender_email: str) -> List[Dict[str, Any]]:
        """Match distributor(s) by sender email (legacy fallback)."""
        email = (sender_email or "").strip().lower()
        if not email:
            return []
        dist = self.distributors.get_by_email(sender_email)
        if dist is not None and dist.is_active and not dist.is_deleted:
            return [
                {
                    "id": dist.id,
                    "company": dist.company,
                    "name": dist.name,
                    "email": dist.email,
                    "match": "exact",
                }
            ]
        matches: List[Dict[str, Any]] = []
        for d in self.distributors.list(skip=0, limit=500):
            if not d.is_active or d.is_deleted:
                continue
            demail = (d.email or "").strip().lower()
            if demail and demail == email:
                matches.append(
                    {
                        "id": d.id,
                        "company": d.company,
                        "name": d.name,
                        "email": d.email,
                        "match": "exact",
                    }
                )
        return matches

    def list_active_distributors(self) -> List[Dict[str, Any]]:
        """Dropdown options when sender does not match."""
        out: List[Dict[str, Any]] = []
        for d in self.distributors.list(skip=0, limit=500):
            if not d.is_active or d.is_deleted:
                continue
            out.append(
                {
                    "id": d.id,
                    "company": d.company,
                    "name": d.name,
                    "email": d.email,
                }
            )
        return out

    def _is_excel_att(self, att: Any) -> bool:
        if getattr(att, "is_deleted", False):
            return False
        if getattr(att, "is_excel", False):
            return True
        return (getattr(att, "file_name", None) or "").lower().endswith((".xlsx", ".xlsm"))

    def _list_excel_attachments(
        self,
        email: Any,
        *,
        limit: int = MAX_EXCEL_ATTACHMENTS_PER_EMAIL,
    ) -> List[Any]:
        """Active Excel attachments for an email, capped at ``limit`` (default 5)."""
        found: List[Any] = []
        for att in email.attachments or []:
            if not self._is_excel_att(att):
                continue
            found.append(att)
            if len(found) >= limit:
                break
        return found

    def _excel_attachment(self, email_id: int):
        """Primary (first) Excel attachment — used by Preview remap UI."""
        email = self.emails.get_or_raise(email_id)
        attachments = self._list_excel_attachments(email)
        if not attachments:
            raise ValidationAppError("No Excel attachment found for this email")
        excel = attachments[0]
        if not excel.file_path or not Path(excel.file_path).is_file():
            raise ValidationAppError(
                "Excel attachment file is missing on disk. Re-sync Outlook to download again."
            )
        return email, excel

    def _rows_by_period(
        self,
        use_rows: List[Dict[str, Any]],
        *,
        company: str,
        quarter: str,
        segment: str = "",
        location: str = "",
    ) -> Dict[str, List[ParsedSalesRow]]:
        from collections import defaultdict

        by_period: Dict[str, List[ParsedSalesRow]] = defaultdict(list)
        for raw in use_rows:
            qty = raw.get("sales_quantity", raw.get("quantity"))
            try:
                if isinstance(qty, Decimal):
                    qty_val, qty_disp = qty, str(qty)
                else:
                    qty_val, qty_disp = parse_quantity(qty)
            except ValueError as exc:
                raise ValidationAppError(f"Invalid quantity in import rows: {exc}") from exc
            customer = str(raw.get("customer_name") or raw.get("customer") or "").strip()
            product = str(raw.get("product") or "").strip()
            if not customer or not product:
                continue
            period = str(
                raw.get("period") or raw.get("reporting_quarter") or quarter or ""
            ).strip()
            if not period:
                continue
            existing = next(
                (
                    r
                    for r in by_period[period]
                    if r.customer_name.casefold() == customer.casefold()
                    and r.product.casefold() == product.casefold()
                ),
                None,
            )
            if existing is not None:
                existing.quantity = Decimal(str(existing.quantity)) + Decimal(str(qty_val))
                existing.quantity_display = str(existing.quantity)
                existing.row_hash = build_sales_row_hash(
                    company,
                    existing.customer_name,
                    existing.segment or segment,
                    existing.product,
                    existing.quantity,
                    period,
                )
                continue
            seg = (segment or "").strip()
            loc = (location or "").strip()
            by_period[period].append(
                ParsedSalesRow(
                    distributor=company,
                    customer_name=customer,
                    segment=seg,
                    location=loc,
                    product=product,
                    quantity=qty_val,
                    quantity_display=qty_disp,
                    period=period,
                    unit="MT",
                    company=company,
                    row_hash=build_sales_row_hash(
                        company, customer, seg, product, qty_val, period
                    ),
                )
            )
        return by_period

    def _resolve_reporting_quarter(
        self,
        email: Any,
        preview: Dict[str, Any],
        *,
        override: Optional[str] = None,
    ) -> str:
        """Pick reporting quarter: explicit override → email cache → AI preview."""
        explicit = (override or "").strip()
        if explicit:
            return explicit
        cached = (getattr(email, "detected_quarter", None) or "").strip()
        if cached:
            return cached
        detected = (preview.get("detected_quarter") or "").strip()
        if detected:
            return detected
        from_rows = [
            str(r.get("period") or r.get("reporting_quarter") or "").strip()
            for r in (preview.get("rows") or [])
        ]
        from_rows = [q for q in from_rows if q]
        if from_rows:
            return from_rows[0]
        raise ValidationAppError(
            "Could not detect reporting quarter from workbook. Open Preview to retry."
        )

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
        actor: str,
        fiscal_year_start: Optional[int],
        overall: float,
    ) -> Tuple[int, bool, Any, List[str], int]:
        """Persist one workbook's rows. Returns inserted, dup, last_report, quarters, reports."""
        path = Path(att.file_path)
        by_period = self._rows_by_period(
            use_rows,
            company=company,
            quarter=quarter,
            segment=segment,
            location=location,
        )
        if not by_period:
            raise ValidationAppError(
                f"No valid rows to import after validation ({att.file_name})"
            )

        total_inserted = 0
        any_dup = False
        last_report = None
        quarters_imported: List[str] = []
        for period, parsed in sorted(by_period.items()):
            report, inserted, was_dup, _quality = self.reports.persist_approved_rows(
                path,
                parsed,
                quality_score=int(round(overall)),
                source=ReportSource.OUTLOOK,
                report_name=f"{email.subject} - {att.file_name} ({period})",
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
            )
            total_inserted += inserted
            any_dup = any_dup or was_dup
            last_report = report
            quarters_imported.append(period)
        return total_inserted, any_dup, last_report, quarters_imported, len(quarters_imported)

    def preview_email(
        self,
        email_id: int,
        *,
        actor: str = "system",
        mapping_override: Optional[Any] = None,
        fiscal_year_start: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Parse the email Excel for AI preview (no import)."""
        from app.services.email_subject_service import EmailSubjectService

        email, att = self._excel_attachment(email_id)
        EmailSubjectService(self.db).apply_to_email(email, actor=actor, skip_if_valid=True)
        if not email.subject_valid:
            raise ValidationAppError(
                email.error_message
                or "Invalid email subject. Expected format: Distributor | Location | Segment",
                details={"email_id": email_id, "subject": email.subject},
            )
        path = Path(att.file_path)

        if mapping_override:
            preview = self._preview_with_override(
                path,
                mapping_override,
                fiscal_year_start=fiscal_year_start,
            )
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.UPDATED,
                    details=(
                        f"ERP Mapping Edited | email_id={email_id} | "
                        f"workbook={att.file_name} | rows={preview.get('row_count', 0)}"
                    ),
                    entity_type="email",
                    entity_id=str(email_id),
                    module="Email Extraction",
                    status="Success",
                    extra_metadata={
                        "workbook": att.file_name,
                        "row_count": preview.get("row_count"),
                        "confidence": (preview.get("confidence") or {}).get("overall"),
                    },
                )
            )
        else:
            preview = self.parser.preview(path, fiscal_year_start=fiscal_year_start)
            preview["available_columns"] = self._available_columns(path, preview.get("sheet_name"))
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.PROCESSED,
                    details=(
                        f"ERP Workbook Parsed | email_id={email_id} | "
                        f"workbook={att.file_name} | sheet={preview.get('sheet_name')} | "
                        f"rows={preview.get('row_count', 0)} | "
                        f"confidence={(preview.get('confidence') or {}).get('overall')}"
                    ),
                    entity_type="email",
                    entity_id=str(email_id),
                    module="Email Extraction",
                    status="Success",
                    extra_metadata={
                        "workbook": att.file_name,
                        "sheet": preview.get("sheet_name"),
                        "row_count": preview.get("row_count"),
                        "confidence": (preview.get("confidence") or {}).get("overall"),
                    },
                )
            )

        subject_match = self.resolve_distributor_from_subject(email)
        sender_matches = self.resolve_distributors_for_sender(email.sender_email)
        matches = [subject_match] if subject_match else sender_matches
        all_excels = self._list_excel_attachments(email)
        detected_q = (preview.get("detected_quarter") or email.detected_quarter or "").strip()
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

    def _available_columns(self, path: Path, sheet_name: Optional[str]) -> List[Dict[str, Any]]:
        """Return header cells for remapping UI. Never pass fake multi-sheet labels."""
        from openpyxl import load_workbook

        from app.erp_parser.workbook_detector import resolve_sheet_name

        real_name = (sheet_name or "").strip()
        # Guard: monthly-sheets display labels like "Apr-25, May-25, Jun-25…"
        if (
            not real_name
            or "," in real_name
            or real_name.endswith("…")
            or real_name.endswith("...")
        ):
            real_name = ""
        else:
            try:
                real_name = resolve_sheet_name(path, real_name)
            except Exception:  # noqa: BLE001
                real_name = ""

        if not real_name:
            try:
                real_name, _ = detect_best_sheet(path, allow_llm_fallback=True)
            except Exception:  # noqa: BLE001
                try:
                    wb = load_workbook(path, read_only=True, data_only=True)
                    names = list(wb.sheetnames)
                    wb.close()
                    real_name = names[0] if names else ""
                except Exception:  # noqa: BLE001
                    return []

        if not real_name:
            return []

        try:
            matrix = read_sheet_matrix(path, real_name)
        except Exception:  # noqa: BLE001
            return []

        # Prefer product-matrix header row when present (Particulars | Product…)
        try:
            from app.erp_parser.monthly_product_sheets import _find_product_header_row

            product_header = _find_product_header_row(matrix)
        except Exception:  # noqa: BLE001
            product_header = None

        if product_header:
            header_row = list(matrix[int(product_header["header_row_index"])]) if matrix else []
        else:
            header_info = detect_header_row(matrix)
            header_row = list(matrix[header_info["header_row_index"]]) if matrix else []

        cols = []
        for i, h in enumerate(header_row):
            text = str(h).strip() if h is not None else ""
            if text:
                cols.append({"index": i, "header": text, "column": i + 1})
        return cols

    def _coerce_override(self, mapping_override: Any) -> Dict[str, Any]:
        if isinstance(mapping_override, list):
            return {"mappings": mapping_override}
        if isinstance(mapping_override, dict):
            if "mappings" in mapping_override:
                return mapping_override
            return mapping_override
        raise ValidationAppError("Invalid mapping override payload")

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

    def _resolve_override_positions(
        self, header_row: Sequence[Any], override: Dict[str, Any]
    ) -> Dict[str, Optional[int]]:
        positions: Dict[str, Optional[int]] = {
            "customer": None,
            "product": None,
            "quantity": None,
        }
        if isinstance(override.get("mappings"), list):
            for item in override["mappings"]:
                mapped = _normalize_mapped_field(str(item.get("mapped") or ""))
                if mapped not in positions:
                    continue
                if item.get("column") is not None:
                    positions[mapped] = int(item["column"]) - 1
                    continue
                if item.get("column_index") is not None:
                    positions[mapped] = int(item["column_index"])
                    continue
                original = normalize_header_text(item.get("original"))
                for i, h in enumerate(header_row):
                    if normalize_header_text(h) == original:
                        positions[mapped] = i
                        break
            return positions

        for field in ("customer", "product", "quantity"):
            raw = override.get(field)
            if raw is None and field == "quantity":
                raw = override.get("sales_quantity")
            if raw is None:
                continue
            if isinstance(raw, int):
                positions[field] = raw - 1 if raw >= 1 else raw
                continue
            text = normalize_header_text(raw)
            for i, h in enumerate(header_row):
                if normalize_header_text(h) == text:
                    positions[field] = i
                    break
        return positions

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
        quarter = (reporting_quarter or "").strip()
        total_inserted = 0
        any_dup = False
        last_report = None
        quarters_imported: List[str] = []
        reports_created = 0
        workbooks_imported: List[str] = []
        workbook_skips: List[Dict[str, Any]] = []
        qualities: List[float] = []

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
                    )
                    use_rows = rows
                else:
                    # Multi-file or subsequent attachments: always re-parse
                    preview = self.parser.preview(
                        path,
                        fiscal_year_start=fiscal_year_start,
                        reporting_quarter=quarter or None,
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

            try:
                inserted, was_dup, report, periods, n_reports = self._persist_preview_rows(
                    email=email,
                    att=att,
                    preview=preview,
                    use_rows=use_rows,
                    distributor_id=resolved_id,
                    company=company,
                    quarter=quarter,
                    segment=segment,
                    location=location,
                    actor=actor,
                    fiscal_year_start=fiscal_year_start,
                    overall=overall,
                )
            except ValidationAppError as exc:
                workbook_skips.append(
                    {"workbook": att.file_name, "reason": str(exc.message)}
                )
                continue

            total_inserted += inserted
            any_dup = any_dup or was_dup
            last_report = report or last_report
            quarters_imported.extend(periods)
            reports_created += n_reports
            workbooks_imported.append(att.file_name or f"attachment-{att.id}")
            qualities.append(overall)
            logger.info(
                "ERP workbook imported | email_id={} | file={} | rows={} | quarters={}",
                email_id,
                att.file_name,
                inserted,
                periods,
            )

        if not workbooks_imported:
            detail = workbook_skips or [{"reason": "no importable Excel attachments"}]
            raise ValidationAppError(
                "No Excel attachments could be imported for this email.",
                details={"skips": detail},
            )

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
