"""Orchestrate ERP workbook → structured sales rows (preview + ingest)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.erp_parser.block_parser import (
    detect_block_product_layout,
    extract_product_blocks_workbook,
)
from app.erp_parser.metadata_parser import (
    detect_metadata_layout,
    extract_metadata_workbook,
)
from app.erp_parser.confidence import compute_erp_confidence
from app.erp_parser.cross_tab import (
    detect_product_month_matrix,
    extract_product_month_matrix_rows,
)
from app.erp_parser.header_detector import detect_header_row
from app.erp_parser.header_mapper import FIELD_DISPLAY, is_month_header, normalize_header_text
from app.erp_parser.llm_header_resolver import (
    LLMHeaderResolver,
    LLMHeaderResolverError,
    sanitize_headers,
    sanitize_sample_rows,
)
from app.erp_parser.monthly_product_sheets import extract_monthly_product_sheets
from app.erp_parser.row_extractor import extract_rows
from app.erp_parser.sheet_detector import detect_best_sheet
from app.erp_parser.workbook_detector import detect_workbook, read_sheet_matrix
from app.exceptions import ExcelProcessingError
from app.schemas.sales_record import ParsedSalesRow
from app.utils.hashing import build_sales_row_hash

logger = get_logger(__name__)

# Call LLM only when Python overall confidence is below this.
LLM_FALLBACK_THRESHOLD = 85.0
# Do not trust weak LLM column guesses.
LLM_MIN_TRUST = 70.0


class ERPParseResult(BaseModel):
    """Structured ERP parse output for preview and ReportService ingest."""

    sheet_name: str = ""
    sheet_score: float = 0.0
    header_row: int = 0
    column_positions: Dict[str, Optional[int]] = Field(default_factory=dict)
    mapping: List[Dict[str, Any]] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    parsed_rows: List[ParsedSalesRow] = Field(default_factory=list)
    expected_rows: int = 0
    imported_rows: int = 0
    incomplete_rows: int = 0
    quality_score: int = 0
    overall_confidence: float = 0.0
    customer_confidence: float = 0.0
    product_confidence: float = 0.0
    quantity_confidence: float = 0.0
    confidence_band: str = "red"
    confidence_breakdown: Dict[str, Any] = Field(default_factory=dict)
    row_errors: List[str] = Field(default_factory=list)
    candidate_sheets: List[str] = Field(default_factory=list)
    # Compatibility fields (no longer template-driven)
    template_detected: bool = False
    sales_table_detected: bool = False
    template_name: str = "erp"
    mapping_strategy: str = "erp_semantic"
    mapping_source: str = "python"  # python | llm
    distributor_details: Dict[str, str] = Field(default_factory=dict)
    reporting_month: Optional[str] = None


def _mapping_complete(
    positions: Dict[str, Optional[int]],
    quantity_columns: Sequence[int],
) -> bool:
    return (
        positions.get("customer") is not None
        and positions.get("product") is not None
        and (positions.get("quantity") is not None or bool(quantity_columns))
    )


def _find_header_index(headers: Sequence[Any], label: Optional[str]) -> Optional[int]:
    if not label:
        return None
    target = str(label).strip().lower()
    if not target:
        return None
    for idx, raw in enumerate(headers):
        if raw is None:
            continue
        if str(raw).strip().lower() == target:
            return idx
    # Fallback: normalized compare
    target_n = normalize_header_text(label)
    for idx, raw in enumerate(headers):
        if normalize_header_text(raw) == target_n:
            return idx
    return None


def _collect_sample_rows(
    matrix: Sequence[Sequence[Any]],
    header_row_index: int,
    header_width: int,
    *,
    limit: int = 3,
) -> List[List[str]]:
    samples: List[List[Any]] = []
    for row in matrix[header_row_index + 1 :]:
        if len(samples) >= limit:
            break
        cells = list(row)[:header_width] if header_width else list(row)
        if any(c is not None and str(c).strip() != "" for c in cells):
            samples.append(cells)
    return sanitize_sample_rows(samples, header_count=header_width, limit=limit)


def _apply_llm_column_map(
    header_row: Sequence[Any],
    llm: Dict[str, Any],
    *,
    python_mapped: Dict[str, Any],
) -> Dict[str, Any]:
    """Replace Customer/Product/Qty positions from LLM column names only."""
    positions = {
        "customer": _find_header_index(header_row, llm.get("customer_column")),
        "product": _find_header_index(header_row, llm.get("product_column")),
        "quantity": _find_header_index(header_row, llm.get("quantity_column")),
    }
    originals = {
        "customer": llm.get("customer_column"),
        "product": llm.get("product_column"),
        "quantity": llm.get("quantity_column"),
    }
    llm_conf = float(llm.get("confidence") or 0)
    confidences = {
        "customer": llm_conf if positions["customer"] is not None else 0.0,
        "product": llm_conf if positions["product"] is not None else 0.0,
        "quantity": llm_conf if positions["quantity"] is not None else 0.0,
    }
    methods = {
        "customer": "llm" if positions["customer"] is not None else "none",
        "product": "llm" if positions["product"] is not None else "none",
        "quantity": "llm" if positions["quantity"] is not None else "none",
    }

    # Preserve monthly-pivot quantity columns when LLM did not pick a qty header,
    # or when it pointed at a month column (keep full month set).
    month_meta = list(python_mapped.get("month_column_meta") or [])
    qty_cols = list(python_mapped.get("quantity_columns") or [])
    qty_idx = positions["quantity"]
    if qty_idx is not None and qty_idx < len(header_row):
        if is_month_header(normalize_header_text(header_row[qty_idx])) and month_meta:
            positions["quantity"] = qty_cols[0] if qty_cols else qty_idx
            originals["quantity"] = "Monthly columns → quarterly totals"
            confidences["quantity"] = max(llm_conf, 95.0)
            methods["quantity"] = "monthly_sum"
        else:
            qty_cols = []
            month_meta = []
    elif qty_cols:
        positions["quantity"] = qty_cols[0]
        originals["quantity"] = "Monthly columns → quarterly totals"
        confidences["quantity"] = max(llm_conf, 95.0)
        methods["quantity"] = "monthly_sum"

    return {
        "positions": positions,
        "originals": originals,
        "confidences": confidences,
        "methods": methods,
        "quantity_columns": qty_cols if methods.get("quantity") == "monthly_sum" else [],
        "month_column_meta": month_meta if methods.get("quantity") == "monthly_sum" else [],
        "llm_confidence": llm_conf,
    }


def _find_header_row_for_llm_labels(
    matrix: Sequence[Sequence[Any]],
    llm: Dict[str, Any],
    *,
    scan_rows: int = 20,
) -> Optional[int]:
    """Locate the row that contains the LLM-identified header labels."""
    labels = [
        str(llm.get(k) or "").strip().lower()
        for k in ("customer_column", "product_column", "quantity_column")
        if llm.get(k)
    ]
    if not labels:
        return None
    limit = min(scan_rows, len(matrix))
    best_idx: Optional[int] = None
    best_hits = 0
    for idx in range(limit):
        row = matrix[idx]
        texts = {
            str(c).strip().lower()
            for c in row
            if c is not None and str(c).strip()
        }
        hits = sum(1 for lab in labels if lab in texts)
        if hits > best_hits:
            best_hits = hits
            best_idx = idx
    if best_hits >= min(2, len(labels)):
        return best_idx
    return None


class ERPParserService:
    """Parse arbitrary distributor ERP Excel into Customer / Product / Qty."""

    def parse_workbook(
        self,
        path: Union[str, Path],
        *,
        sheet_name: Optional[str] = None,
        distributor_label: str = "",
        reporting_quarter: Optional[str] = None,
        fiscal_year_start: Optional[int] = None,
        allow_llm_fallback: bool = True,
    ) -> ERPParseResult:
        """
        Full ERP parse pipeline.

        Primary engine: Python (openpyxl + RapidFuzz).
        LLM is only consulted when overall confidence < 85 (header mapping).
        """
        file_path = Path(path)
        logger.info("ERP parse start | path={}", file_path)

        wb_info = detect_workbook(file_path)
        candidates = wb_info["candidate_sheets"]

        # Kemco metadata: Item Group product, before header mapping and the LLM.
        meta_names = [sheet_name] if sheet_name else list(candidates)
        meta_layout = False
        for meta_name in meta_names:
            if not meta_name:
                continue
            try:
                meta_matrix = read_sheet_matrix(file_path, meta_name)
            except Exception:  # noqa: BLE001
                continue
            if detect_metadata_layout(meta_matrix):
                meta_layout = True
                break
        if meta_layout:
            metadata = extract_metadata_workbook(
                file_path,
                fiscal_year_start=fiscal_year_start,
                reporting_quarter=reporting_quarter,
                sheet_name=sheet_name,
            )
            if metadata and metadata.get("detected"):
                if not metadata.get("rows"):
                    raise ExcelProcessingError(
                        "ERP Metadata Parser activated but no sales rows were extracted."
                    )
                field_conf = {"customer": 98.0, "product": 98.0, "quantity": 96.0}
                confidence = compute_erp_confidence(
                    field_confidences=field_conf,
                    sheet_score=float(metadata.get("score") or 90),
                    extracted_rows=len(metadata["rows"]),
                    quantity_ok=metadata["quantity_ok"],
                    quantity_fail=metadata["quantity_fail"],
                    skipped_invalid=metadata["skipped_invalid"],
                )
                active_mapped = {
                    "positions": {"customer": 0, "product": None, "quantity": 1},
                    "originals": {
                        "customer": "Account Name",
                        "product": "Item Group",
                        "quantity": "Nett Sale Qty.",
                    },
                    "confidences": field_conf,
                    "methods": {
                        "customer": "metadata",
                        "product": "metadata",
                        "quantity": "metadata",
                    },
                    "quantity_columns": [],
                    "month_column_meta": [],
                }
                sheet_dist = str(metadata.get("distributor") or "").strip()
                return self._finalize_result(
                    chosen=metadata.get("sheet_name") or "Sales Analysis",
                    sheet_score=float(metadata.get("score") or 90),
                    header_row=int(metadata.get("header_row") or 1),
                    active_mapped=active_mapped,
                    active_extracted=metadata,
                    confidence=confidence,
                    mapping_source="python",
                    candidates=candidates,
                    distributor_label=distributor_label or sheet_dist,
                    reporting_quarter=reporting_quarter,
                    python_overall=float(confidence["overall_confidence"]),
                )

        # BPS product blocks: decide before header mapping, RapidFuzz, and the LLM.
        block_names = [sheet_name] if sheet_name else list(candidates)
        block_layout = False
        for block_name in block_names:
            if not block_name:
                continue
            try:
                block_matrix = read_sheet_matrix(file_path, block_name)
            except Exception:  # noqa: BLE001
                continue
            if detect_block_product_layout(block_matrix):
                block_layout = True
                break
        product_blocks = None
        if block_layout:
            product_blocks = extract_product_blocks_workbook(
                file_path,
                fiscal_year_start=fiscal_year_start,
                reporting_quarter=reporting_quarter,
                sheet_name=sheet_name,
            )
        if product_blocks and product_blocks.get("detected"):
            if not product_blocks.get("rows"):
                raise ExcelProcessingError(
                    "ERP Block Parser activated but no sales rows were extracted."
                )
            field_conf = {"customer": 97.0, "product": 97.0, "quantity": 95.0}
            confidence = compute_erp_confidence(
                field_confidences=field_conf,
                sheet_score=float(product_blocks.get("score") or 85),
                extracted_rows=len(product_blocks["rows"]),
                quantity_ok=product_blocks["quantity_ok"],
                quantity_fail=product_blocks["quantity_fail"],
                skipped_invalid=product_blocks["skipped_invalid"],
            )
            primary_sheet = product_blocks.get("sheet_name") or "product blocks"
            active_mapped = {
                "positions": {"customer": 0, "product": None, "quantity": None},
                "originals": {
                    "customer": "Party",
                    "product": "Product block title",
                    "quantity": "Month columns",
                },
                "confidences": field_conf,
                "methods": {
                    "customer": "product_blocks",
                    "product": "product_blocks",
                    "quantity": "product_blocks",
                },
                "quantity_columns": [],
                "month_column_meta": [],
            }
            return self._finalize_result(
                chosen=primary_sheet,
                sheet_score=float(product_blocks.get("score") or 85),
                header_row=1,
                active_mapped=active_mapped,
                active_extracted=product_blocks,
                confidence=confidence,
                mapping_source="python",
                candidates=candidates,
                distributor_label=distributor_label,
                reporting_quarter=reporting_quarter,
                python_overall=float(confidence["overall_confidence"]),
            )

        # Multi-sheet monthly product matrix (NORTH CHOWDHRY: Apr-25…Mar-26 tabs)
        monthly_sheets = extract_monthly_product_sheets(
            file_path,
            fiscal_year_start=fiscal_year_start,
            reporting_quarter=reporting_quarter,
        )
        if monthly_sheets and monthly_sheets.get("rows"):
            field_conf = {"customer": 96.0, "product": 96.0, "quantity": 94.0}
            confidence = compute_erp_confidence(
                field_confidences=field_conf,
                sheet_score=float(monthly_sheets.get("score") or 80),
                extracted_rows=len(monthly_sheets["rows"]),
                quantity_ok=monthly_sheets["quantity_ok"],
                quantity_fail=monthly_sheets["quantity_fail"],
                skipped_invalid=monthly_sheets["skipped_invalid"],
            )
            sheets_used = monthly_sheets.get("sheets_used") or []
            sheet_label = ", ".join(sheets_used[:3]) + ("…" if len(sheets_used) > 3 else "")
            primary_sheet = sheets_used[0] if sheets_used else "monthly sheets"
            active_mapped = {
                "positions": {"customer": 0, "product": None, "quantity": None},
                "originals": {
                    "customer": "Particulars",
                    "product": "Product columns per month sheet",
                    "quantity": "Month sheets → quarterly totals",
                },
                "confidences": field_conf,
                "methods": {
                    "customer": "monthly_sheets",
                    "product": "monthly_sheets",
                    "quantity": "monthly_sum",
                },
                "quantity_columns": [],
                "month_column_meta": [],
            }
            logger.info(
                "ERP monthly product sheets detected | sheets={} | rows={} | score={}",
                len(sheets_used),
                len(monthly_sheets["rows"]),
                monthly_sheets.get("score"),
            )
            result = self._finalize_result(
                chosen=primary_sheet,
                sheet_score=float(monthly_sheets.get("score") or 80),
                header_row=1,
                active_mapped=active_mapped,
                active_extracted=monthly_sheets,
                confidence=confidence,
                mapping_source="python",
                candidates=candidates,
                distributor_label=distributor_label,
                reporting_quarter=reporting_quarter,
                python_overall=float(confidence["overall_confidence"]),
            )
            # Keep a human label for UI without breaking sheet lookups
            if sheet_label and sheet_label != primary_sheet:
                result.sheet_name = primary_sheet
                result.confidence_breakdown = {
                    **(result.confidence_breakdown or {}),
                    "sheet_label": sheet_label,
                    "sheets_used": sheets_used,
                }
            return result

        if sheet_name:
            try:
                from app.erp_parser.workbook_detector import resolve_sheet_name

                chosen = resolve_sheet_name(file_path, sheet_name)
                from app.erp_parser.sheet_detector import score_sheet

                sheet_score = score_sheet(read_sheet_matrix(file_path, chosen))
            except Exception:  # noqa: BLE001
                chosen, sheet_score = detect_best_sheet(
                    file_path, allow_llm_fallback=allow_llm_fallback
                )
        else:
            chosen, sheet_score = detect_best_sheet(
                file_path, allow_llm_fallback=allow_llm_fallback
            )

        try:
            matrix = read_sheet_matrix(file_path, chosen)
        except Exception as exc:  # noqa: BLE001
            if not allow_llm_fallback:
                raise ExcelProcessingError(f"Unable to read sheet '{chosen}': {exc}") from exc
            try:
                from app.erp_parser.llm_sheet_resolver import LLMSheetResolver

                chosen, sheet_score = LLMSheetResolver().pick_sheet(
                    file_path, candidates=candidates
                )
                matrix = read_sheet_matrix(file_path, chosen)
            except Exception as llm_exc:  # noqa: BLE001
                raise ExcelProcessingError(
                    f"Unable to open a sales sheet in this workbook: {llm_exc}"
                ) from llm_exc
        if not matrix:
            raise ExcelProcessingError(f"Sheet '{chosen}' has no readable cells")

        header_info = detect_header_row(matrix)
        mapped = header_info["mapping"]
        positions_0 = dict(mapped["positions"])
        quantity_columns = list(mapped.get("quantity_columns") or [])
        month_column_meta = list(mapped.get("month_column_meta") or [])
        header_idx = header_info["header_row_index"]
        header_row = list(matrix[header_idx]) if matrix else []

        # Product×month cross-tab (EAST ARIEN-style) — prefer when standard triad is incomplete
        matrix_layout = detect_product_month_matrix(matrix)
        python_complete = _mapping_complete(positions_0, quantity_columns)
        python_extracted: Optional[Dict[str, Any]] = None
        python_confidence: Optional[Dict[str, Any]] = None
        python_overall = 0.0
        mapping_source = "python"
        active_mapped = mapped
        active_extracted: Optional[Dict[str, Any]] = None
        active_confidence: Optional[Dict[str, Any]] = None

        if matrix_layout and (not python_complete or float(matrix_layout.get("score") or 0) >= 70):
            matrix_extracted = extract_product_month_matrix_rows(
                matrix,
                layout=matrix_layout,
                fiscal_year_start=fiscal_year_start,
                reporting_quarter=reporting_quarter,
            )
            if matrix_extracted.get("rows"):
                field_conf = {"customer": 95.0, "product": 95.0, "quantity": 92.0}
                matrix_confidence = compute_erp_confidence(
                    field_confidences=field_conf,
                    sheet_score=max(sheet_score, float(matrix_layout.get("score") or 0)),
                    extracted_rows=len(matrix_extracted["rows"]),
                    quantity_ok=matrix_extracted["quantity_ok"],
                    quantity_fail=matrix_extracted["quantity_fail"],
                    skipped_invalid=matrix_extracted["skipped_invalid"],
                )
                # Synthetic mapping for preview UI
                active_mapped = {
                    "positions": {
                        "customer": int(matrix_layout["customer_col"]),
                        "product": None,
                        "quantity": None,
                    },
                    "originals": {
                        "customer": "PARTICULARS / Customer",
                        "product": "Product column groups",
                        "quantity": "Monthly columns → quarterly totals",
                    },
                    "confidences": field_conf,
                    "methods": {
                        "customer": "cross_tab",
                        "product": "cross_tab",
                        "quantity": "monthly_sum",
                    },
                    "quantity_columns": [
                        m["column"] for m in (matrix_layout.get("month_column_meta") or [])
                    ],
                    "month_column_meta": list(matrix_layout.get("month_column_meta") or []),
                }
                active_extracted = matrix_extracted
                active_confidence = matrix_confidence
                python_overall = float(matrix_confidence["overall_confidence"])
                python_complete = True
                mapping_source = "python"
                header_idx = int(matrix_layout["header_row_index"])
                header_info = {
                    **header_info,
                    "header_row": int(matrix_layout["header_row"]),
                    "header_row_index": header_idx,
                }
                logger.info(
                    "ERP cross-tab layout detected | products={} | rows={} | score={}",
                    len(matrix_layout.get("groups") or []),
                    len(matrix_extracted["rows"]),
                    matrix_layout.get("score"),
                )

        if active_extracted is None and python_complete:
            python_extracted = extract_rows(
                matrix,
                header_row_index=header_idx,
                positions=positions_0,
                quantity_columns=quantity_columns or None,
                month_column_meta=month_column_meta or None,
                fiscal_year_start=fiscal_year_start,
                reporting_quarter=reporting_quarter,
            )
            if python_extracted["rows"]:
                python_confidence = compute_erp_confidence(
                    field_confidences=mapped["confidences"],
                    sheet_score=sheet_score,
                    extracted_rows=len(python_extracted["rows"]),
                    quantity_ok=python_extracted["quantity_ok"],
                    quantity_fail=python_extracted["quantity_fail"],
                    skipped_invalid=python_extracted["skipped_invalid"],
                )
                python_overall = float(python_confidence["overall_confidence"])
                active_mapped = mapped
                active_extracted = python_extracted
                active_confidence = python_confidence

        need_llm = False
        block_ready = bool(
            active_extracted
            and active_extracted.get("rows")
            and active_extracted.get("layout") == "product_blocks"
        )
        if allow_llm_fallback and not block_ready and not (
            matrix_layout and active_extracted and active_extracted.get("rows")
        ):
            need_llm = (
                active_extracted is None
                or not active_extracted.get("rows")
                or active_confidence is None
                or python_overall < LLM_FALLBACK_THRESHOLD
            )

        if need_llm:
            llm_applied = self._try_llm_header_fallback(
                matrix=matrix,
                header_row=header_row,
                header_idx=header_idx,
                python_mapped=mapped,
                sheet_score=sheet_score,
                fiscal_year_start=fiscal_year_start,
                reporting_quarter=reporting_quarter,
                python_overall=python_overall,
            )
            if llm_applied is not None:
                active_mapped, active_extracted, active_confidence, mapping_source = llm_applied

        # Cross-tab results are complete even without classic triad positions
        mapping_ok = bool(
            active_extracted
            and active_extracted.get("rows")
            and active_confidence is not None
            and (
                active_extracted.get("layout") in {
                    "product_month_matrix",
                    "monthly_product_sheets",
                    "product_blocks",
                }
                or _mapping_complete(
                    active_mapped["positions"],
                    active_mapped.get("quantity_columns") or [],
                )
            )
        )
        if not mapping_ok:
            raise ExcelProcessingError(
                "Could not map Customer, Product, and Sales Quantity columns. "
                "Please verify the ERP export has recognizable headers."
            )

        return self._finalize_result(
            chosen=chosen,
            sheet_score=sheet_score,
            header_row=header_info["header_row"],
            active_mapped=active_mapped,
            active_extracted=active_extracted,
            confidence=active_confidence,
            mapping_source=mapping_source,
            candidates=candidates,
            distributor_label=distributor_label,
            reporting_quarter=reporting_quarter,
            python_overall=python_overall,
        )

    def _finalize_result(
        self,
        *,
        chosen: str,
        sheet_score: float,
        header_row: int,
        active_mapped: Dict[str, Any],
        active_extracted: Dict[str, Any],
        confidence: Dict[str, Any],
        mapping_source: str,
        candidates: List[str],
        distributor_label: str,
        reporting_quarter: Optional[str],
        python_overall: float,
    ) -> ERPParseResult:
        raw_rows: List[Dict[str, Any]] = active_extracted["rows"]

        mapping_list: List[Dict[str, Any]] = []
        for field in ("customer", "product", "quantity"):
            mapping_list.append(
                {
                    "field": field,
                    "original": active_mapped["originals"].get(field),
                    "mapped": FIELD_DISPLAY[field],
                    "confidence": active_mapped["confidences"].get(field, 0),
                    "method": active_mapped["methods"].get(field, "none"),
                    "column": (
                        active_mapped["positions"][field] + 1
                        if active_mapped["positions"].get(field) is not None
                        else None
                    ),
                }
            )

        dist_label = (distributor_label or "").strip()
        quarter = (reporting_quarter or "").strip() or None
        parsed_rows: List[ParsedSalesRow] = []
        for raw in raw_rows:
            qty = raw["sales_quantity"]
            if not isinstance(qty, Decimal):
                qty = Decimal(str(qty))
            row_period = str(raw.get("period") or raw.get("reporting_quarter") or quarter or "").strip() or None
            source_month = str(raw.get("source_month") or "").strip() or None
            original_unit = str(raw.get("original_unit") or "").strip() or None
            row = ParsedSalesRow(
                sr_no=None,
                distributor=dist_label,
                customer_name=raw["customer_name"],
                segment="",
                product=raw["product"],
                quantity=qty,
                quantity_display=str(raw.get("sales_quantity_display") or qty),
                period=row_period,
                source_month=source_month,
                unit="MT",
                original_unit=original_unit,
                company=None,
                row_hash="",
                errors=[],
            )
            row.row_hash = build_sales_row_hash(
                dist_label,
                row.customer_name,
                row.segment,
                row.product,
                row.quantity,
                row.period or "",
                source_month or "",
            )
            parsed_rows.append(row)

        column_positions = {
            field: (
                active_mapped["positions"][field] + 1
                if active_mapped["positions"].get(field) is not None
                else None
            )
            for field in ("customer", "product", "quantity")
        }

        quality = int(round(confidence["overall_confidence"]))
        result = ERPParseResult(
            sheet_name=chosen,
            sheet_score=sheet_score,
            header_row=header_row,
            column_positions=column_positions,
            mapping=mapping_list,
            rows=[
                {
                    "customer_name": r["customer_name"],
                    "product": r["product"],
                    "sales_quantity": float(r["sales_quantity"]),
                    **(
                        {"period": r["period"], "reporting_quarter": r["period"]}
                        if r.get("period")
                        else {}
                    ),
                    **(
                        {"source_month": r["source_month"]}
                        if r.get("source_month")
                        else {}
                    ),
                    **(
                        {"original_unit": r["original_unit"]}
                        if r.get("original_unit")
                        else {}
                    ),
                }
                for r in raw_rows
            ],
            parsed_rows=parsed_rows,
            expected_rows=len(raw_rows) + int(active_extracted.get("skipped_invalid") or 0),
            imported_rows=len(raw_rows),
            incomplete_rows=int(active_extracted.get("skipped_invalid") or 0),
            quality_score=quality,
            overall_confidence=confidence["overall_confidence"],
            customer_confidence=confidence["customer_confidence"],
            product_confidence=confidence["product_confidence"],
            quantity_confidence=confidence["quantity_confidence"],
            confidence_band=confidence["band"],
            confidence_breakdown={
                **confidence,
                "fiscal_year_start": active_extracted.get("fiscal_year_start"),
                "monthly_pivot": active_extracted.get("monthly_pivot"),
                "layout": active_extracted.get("layout"),
                "mapping_source": mapping_source,
                "python_confidence": python_overall,
                "layout": active_extracted.get("layout"),
            },
            row_errors=active_extracted.get("errors") or [],
            candidate_sheets=candidates,
            sales_table_detected=True,
            mapping_source=mapping_source,
            reporting_month=quarter,
            distributor_details={},
        )
        logger.info(
            "ERP parse complete | sheet={} | rows={} | confidence={} | band={} | source={}",
            chosen,
            len(raw_rows),
            quality,
            confidence["band"],
            mapping_source,
        )
        return result

    def _try_llm_header_fallback(
        self,
        *,
        matrix: Sequence[Sequence[Any]],
        header_row: Sequence[Any],
        header_idx: int,
        python_mapped: Dict[str, Any],
        sheet_score: float,
        fiscal_year_start: Optional[int],
        reporting_quarter: Optional[str],
        python_overall: float,
    ) -> Optional[tuple]:
        """
        Call LLM header resolver; return (mapped, extracted, confidence, 'llm')
        or None to keep Python result.
        """
        try:
            # When Python mapping is weak, prefer a dense text row for the LLM payload
            payload_idx = header_idx
            payload_row = list(header_row)
            if python_overall < LLM_FALLBACK_THRESHOLD:
                best_density = sum(
                    1 for c in payload_row if c is not None and str(c).strip() and not str(c).strip().replace(".", "", 1).isdigit()
                )
                for idx, row in enumerate(matrix[:20]):
                    density = sum(
                        1
                        for c in row
                        if c is not None and str(c).strip() and not str(c).strip().replace(".", "", 1).isdigit()
                    )
                    if density > best_density:
                        best_density = density
                        payload_idx = idx
                        payload_row = list(row)

            headers = sanitize_headers(payload_row)
            samples = _collect_sample_rows(matrix, payload_idx, len(headers))
            llm_result = LLMHeaderResolver().resolve_headers(headers, samples)
        except LLMHeaderResolverError as exc:
            logger.warning("LLM Header Resolver Failed | err={}", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM Header Resolver Failed | err={}", exc)
            return None

        llm_conf = float(llm_result.get("confidence") or 0)
        if llm_conf < LLM_MIN_TRUST:
            logger.info(
                "LLM Header Resolver confidence below trust floor | llm={} | keep python",
                llm_conf,
            )
            return None

        # Prefer the sheet row that actually contains the LLM header labels
        # (guards against Python mis-picking a data row as the header).
        llm_header_idx = _find_header_row_for_llm_labels(matrix, llm_result)
        use_idx = header_idx if llm_header_idx is None else llm_header_idx
        use_header_row = list(matrix[use_idx]) if matrix else list(header_row)

        remapped = _apply_llm_column_map(use_header_row, llm_result, python_mapped=python_mapped)
        if not _mapping_complete(remapped["positions"], remapped.get("quantity_columns") or []):
            logger.warning(
                "LLM Header Resolver Failed | err=incomplete column map after LLM"
            )
            return None

        try:
            extracted = extract_rows(
                matrix,
                header_row_index=use_idx,
                positions=remapped["positions"],
                quantity_columns=remapped.get("quantity_columns") or None,
                month_column_meta=remapped.get("month_column_meta") or None,
                fiscal_year_start=fiscal_year_start,
                reporting_quarter=reporting_quarter,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM Header Resolver Failed | err=re-extract: {}", exc)
            return None

        if not extracted.get("rows"):
            logger.warning("LLM Header Resolver Failed | err=no rows after LLM remap")
            return None

        confidence = compute_erp_confidence(
            field_confidences=remapped["confidences"],
            sheet_score=sheet_score,
            extracted_rows=len(extracted["rows"]),
            quantity_ok=extracted["quantity_ok"],
            quantity_fail=extracted["quantity_fail"],
            skipped_invalid=extracted["skipped_invalid"],
        )
        # Prefer the better of Python vs LLM (Part 5)
        blended = max(python_overall, float(confidence["overall_confidence"]), llm_conf)
        blended = round(min(100.0, blended), 1)
        confidence = {
            **confidence,
            "overall_confidence": blended,
            "accuracy": blended,
            "llm_confidence": llm_conf,
            "python_confidence": python_overall,
        }
        # Keep band aligned with blended score
        if blended >= 90:
            confidence["band"] = "green"
        elif blended >= 75:
            confidence["band"] = "yellow"
        else:
            confidence["band"] = "red"

        logger.info(
            "LLM Header Resolver applied | llm_conf={} | blended={} | python={}",
            llm_conf,
            blended,
            python_overall,
        )
        return remapped, extracted, confidence, "llm"

    def preview(
        self,
        path: Union[str, Path],
        *,
        fiscal_year_start: Optional[int] = None,
        reporting_quarter: Optional[str] = None,
        allow_llm_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Preview-only payload for ``POST /api/erp/parse-preview``.

        ``allow_llm_fallback`` defaults True for explicit Preview/Approve paths.
        Pass False for background scoring (email list / sync) to avoid OpenAI cost.
        """
        result = self.parse_workbook(
            path,
            fiscal_year_start=fiscal_year_start,
            reporting_quarter=reporting_quarter,
            allow_llm_fallback=allow_llm_fallback,
        )
        breakdown = result.confidence_breakdown or {}
        block_mode = breakdown.get("layout") in {"product_blocks", "metadata_sales"}
        quarter_hit = None
        if not block_mode:
            try:
                from app.erp_parser.quarter_detector import detect_reporting_quarter

                quarter_hit = detect_reporting_quarter(
                    path,
                    allow_llm_fallback=allow_llm_fallback,
                )
            except Exception:  # noqa: BLE001
                quarter_hit = None

        detected_quarter = (quarter_hit or {}).get("reporting_quarter")
        if block_mode and not detected_quarter:
            for raw in result.rows or []:
                if raw.get("period"):
                    detected_quarter = raw.get("period")
                    break
        quarter_confidence = float((quarter_hit or {}).get("confidence") or 0)

        return {
            "sheet_name": result.sheet_name,
            "sheet_score": result.sheet_score,
            "header_row": result.header_row,
            "confidence": {
                "overall": result.overall_confidence,
                "accuracy": result.overall_confidence,
                "customer": result.customer_confidence,
                "product": result.product_confidence,
                "quantity": result.quantity_confidence,
                "band": result.confidence_band,
                "breakdown": breakdown,
            },
            "accuracy": result.overall_confidence,
            "mapping": result.mapping,
            "mapping_source": result.mapping_source,
            "column_positions": result.column_positions,
            "rows": result.rows,
            "row_count": len(result.rows),
            "candidate_sheets": result.candidate_sheets,
            "errors": result.row_errors,
            "monthly_pivot": bool(breakdown.get("monthly_pivot")),
            "fiscal_year_start": breakdown.get("fiscal_year_start"),
            "detected_quarter": detected_quarter,
            "quarter_confidence": quarter_confidence,
        }
