"""Excel attachment checks and column override validation."""

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

class ValidationMixin:
    def _is_excel_att(self, att: Any) -> bool:
        if getattr(att, "is_deleted", False):
            return False
        if getattr(att, "is_excel", False):
            return True
        if not (getattr(att, "file_name", None) or "").lower().endswith(
            (".xlsx", ".xlsm", ".xls", ".pdf", ".docx")
        ):
            return False
        return True

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
            raise ValidationAppError("No Excel, PDF, or Word attachment found for this email")
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
        source_unit: str = "MT",
    ) -> Dict[str, List[ParsedSalesRow]]:
        from collections import defaultdict

        by_period: Dict[str, List[ParsedSalesRow]] = defaultdict(list)
        for raw in use_rows:
            qty = raw.get("sales_quantity")
            if qty is None:
                qty = raw.get("sales_qty")
            if qty is None:
                qty = raw.get("quantity")
            if qty is None:
                qty = raw.get("qty")
            row_unit = str(raw.get("original_unit") or "").strip()
            if qty is None or str(qty).strip() == "":
                logger.warning(
                    "Quantity missing; row not inserted | customer={} | product={}",
                    raw.get("customer_name") or raw.get("customer"),
                    raw.get("product"),
                )
                continue
            try:
                if isinstance(qty, Decimal):
                    qty_val = qty
                else:
                    qty_val, _qty_disp = parse_quantity(qty)
            except ValueError as exc:
                logger.warning(
                    "Quantity not parsed; row not inserted | customer={} | product={} | raw={!r} | err={}",
                    raw.get("customer_name") or raw.get("customer"),
                    raw.get("product"),
                    qty,
                    exc,
                )
                continue
            if qty_val < 0:
                logger.warning(
                    "Quantity is negative; row not inserted | customer={} | product={} | raw={!r}",
                    raw.get("customer_name") or raw.get("customer"),
                    raw.get("product"),
                    qty,
                )
                continue
            applied_unit = row_unit or source_unit or "MT"
            qty_disp = format_quantity(qty_val)
            logger.info("DB Value:\n{}", qty_val)
            customer = str(raw.get("customer_name") or raw.get("customer") or "").strip()
            product = str(raw.get("product") or "").strip()
            if not customer or not product:
                continue
            period = str(
                raw.get("period") or raw.get("reporting_quarter") or quarter or ""
            ).strip()
            if not period:
                continue
            source_month = str(raw.get("source_month") or "").strip()
            if not source_month:
                # Derive calendar month from transaction date so PDF months never collapse.
                from app.services.incremental_upload import transaction_date_of

                derived = transaction_date_of(raw)
                if derived:
                    source_month = derived
                    raw["source_month"] = derived
            existing = next(
                (
                    r
                    for r in by_period[period]
                    if r.customer_name.casefold() == customer.casefold()
                    and r.product.casefold() == product.casefold()
                    and (r.source_month or "") == source_month
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
                    existing.source_month or "",
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
                    source_month=source_month or None,
                    unit=(
                        "KG"
                        if str(applied_unit).strip().upper().startswith("KG")
                        else "UNITS"
                        if str(applied_unit).strip().upper() in {"UNIT", "UNITS"}
                        else "MT"
                    ),
                    original_unit=(row_unit or source_unit or "MT").strip().upper() or "MT",
                    company=company,
                    row_hash=build_sales_row_hash(
                        company, customer, seg, product, qty_val, period, source_month
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

    @staticmethod
    def _business_qty(quantity: object) -> str:
        return str(Decimal(str(quantity or 0)).quantize(Decimal("0.001")))

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

