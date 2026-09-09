"""ERP email preview + approved import workflow."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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

    def resolve_distributors_for_sender(self, sender_email: str) -> List[Dict[str, Any]]:
        """Match distributor(s) by sender email (never from Excel)."""
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

    def _excel_attachment(self, email_id: int):
        email = self.emails.get_or_raise(email_id)
        excel = None
        for att in email.attachments or []:
            if getattr(att, "is_deleted", False):
                continue
            if att.is_excel or (att.file_name or "").lower().endswith((".xlsx", ".xlsm")):
                excel = att
                break
        if excel is None:
            raise ValidationAppError("No Excel attachment found for this email")
        if not excel.file_path or not Path(excel.file_path).is_file():
            raise ValidationAppError(
                "Excel attachment file is missing on disk. Re-sync Outlook to download again."
            )
        return email, excel

    def preview_email(
        self,
        email_id: int,
        *,
        actor: str = "system",
        mapping_override: Optional[Any] = None,
        fiscal_year_start: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Parse the email Excel for AI preview (no import)."""
        email, att = self._excel_attachment(email_id)
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

        matches = self.resolve_distributors_for_sender(email.sender_email)
        preview["email_id"] = email.id
        preview["workbook_name"] = att.file_name
        preview["subject"] = email.subject
        preview["sender_email"] = email.sender_email
        preview["sender_name"] = email.sender_name
        preview["distributor_matches"] = matches
        preview["all_distributors"] = self.list_active_distributors()
        preview["distributor_id"] = matches[0]["id"] if len(matches) == 1 else None
        preview["distributor_unknown"] = len(matches) == 0
        preview["import_allowed"] = float((preview.get("confidence") or {}).get("overall") or 0) >= 75

        if email.process_status not in {
            EmailProcessStatus.INSERTED.value,
            EmailProcessStatus.MARKED_READ.value,
        }:
            email.process_status = EmailProcessStatus.PARSED.value
            conf = (preview.get("confidence") or {}).get("overall")
            if conf is not None:
                email.confidence_score = int(round(float(conf)))
            email.error_message = None
            self.db.flush()

        return preview

    def _available_columns(self, path: Path, sheet_name: Optional[str]) -> List[Dict[str, Any]]:
        if not sheet_name:
            sheet_name, _ = detect_best_sheet(path)
        matrix = read_sheet_matrix(path, sheet_name)
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
        distributor_id: int,
        reporting_quarter: str,
        actor: str,
        mapping: Optional[Any] = None,
        rows: Optional[List[Dict[str, Any]]] = None,
        fiscal_year_start: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Persist approved ERP rows after accuracy + mapping review.

        Monthly-pivot workbooks expand into multiple FY quarters — one report
        per quarter under Year → Quarter → Distributor.
        """
        from collections import defaultdict

        email, att = self._excel_attachment(email_id)
        quarter = (reporting_quarter or "").strip()
        if not quarter and not fiscal_year_start:
            raise ValidationAppError("reporting_quarter is required (e.g. Q3 2026)")

        dist = self.distributors.get_or_raise(distributor_id)
        if not dist.is_active or dist.is_deleted:
            raise ValidationAppError("Distributor is inactive")

        path = Path(att.file_path)
        if mapping:
            preview = self._preview_with_override(
                path, mapping, fiscal_year_start=fiscal_year_start, reporting_quarter=quarter or None
            )
        else:
            preview = self.parser.preview(
                path,
                fiscal_year_start=fiscal_year_start,
                reporting_quarter=quarter or None,
            )

        overall = float((preview.get("confidence") or {}).get("overall") or 0)
        if overall < 75:
            raise ValidationAppError(
                "Low accuracy detected. Please review column mappings before importing.",
                details={"overall_confidence": overall},
            )

        use_rows = preview.get("rows") or rows or []
        if not use_rows:
            raise ValidationAppError("No rows to import")

        company = (dist.company or dist.name or "").strip()
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
            by_period[period].append(
                ParsedSalesRow(
                    distributor=company,
                    customer_name=customer,
                    segment="",
                    product=product,
                    quantity=qty_val,
                    quantity_display=qty_disp,
                    period=period,
                    unit="MT",
                    company=company,
                    row_hash=build_sales_row_hash(
                        company, customer, "", product, qty_val, period
                    ),
                )
            )

        if not by_period:
            raise ValidationAppError("No valid rows to import after validation")

        total_inserted = 0
        any_dup = False
        last_report = None
        quarters_imported: List[str] = []
        for period, parsed in sorted(by_period.items()):
            report, inserted, was_dup, quality = self.reports.persist_approved_rows(
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

        email.process_status = EmailProcessStatus.INSERTED.value
        email.confidence_score = int(round(overall))
        email.error_message = None
        self.db.flush()

        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.PROCESSED,
                details=(
                    f"ERP Report Imported | email_id={email_id} | "
                    f"distributor={company} | quarters={quarters_imported} | "
                    f"workbook={att.file_name} | rows={total_inserted}"
                ),
                entity_type="report",
                entity_id=str(last_report.id if last_report else ""),
                module="Email Extraction",
                status="Success",
                report_name=att.file_name,
                extra_metadata={
                    "email_id": email_id,
                    "distributor_id": distributor_id,
                    "distributor": company,
                    "quarters_imported": quarters_imported,
                    "workbook": att.file_name,
                    "row_count": total_inserted,
                    "duplicate": any_dup,
                },
            )
        )

        return {
            "report_id": last_report.id if last_report else 0,
            "records_inserted": total_inserted,
            "duplicate": any_dup,
            "quality_score": int(round(overall)),
            "distributor_id": distributor_id,
            "reporting_quarter": ", ".join(quarters_imported) if len(quarters_imported) > 1 else (quarters_imported[0] if quarters_imported else quarter),
            "workbook_name": att.file_name,
            "reports_created": len(quarters_imported),
            "quarters_imported": quarters_imported,
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
