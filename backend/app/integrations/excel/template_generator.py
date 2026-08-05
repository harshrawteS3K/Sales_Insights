"""Distributor Excel template generator matching the official APCOTEX layout."""

import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.constants import DISTRIBUTOR_TEMPLATE_FILENAME, DISTRIBUTOR_TEMPLATE_SHEET
from app.core.config import settings
from app.core.logging import get_logger
from app.services.excel_dropdown_service import ExcelDropdownService
from app.utils.files import ensure_dir

logger = get_logger(__name__)


class ExcelTemplateGenerator:
    """Generate distributor sales Excel templates with dropdown lists."""

    # Finalized APCOTEX sales table column order
    HEADERS = [
        "Sr. No.",
        "Name of Customer",
        "Segment",
        "Product",
        "Opening Stock",
        "Closing Stock",
        "Quantity",
    ]

    def __init__(self, dropdowns: Optional[ExcelDropdownService] = None) -> None:
        self.dropdowns = dropdowns or ExcelDropdownService()

    def generate(
        self,
        *,
        customers: Sequence[str],
        products_by_segment: Optional[Dict[str, Sequence[str]]] = None,
        products: Optional[Sequence[str]] = None,
        segments: Optional[Sequence[str]] = None,
        distributors: Optional[Sequence[str]] = None,
        output_path: Optional[Path] = None,
        periods: Optional[Sequence[str]] = None,
    ) -> Path:
        """
        Create a blank distributor sales template workbook.

        Layout:
          Rows 1–5  Distributor Details (blank values)
          Row 6     Instruction strip (Segment → Product dependency)
          Row 7     Sales table headers
          Row 8+    Sales data entry rows

        Dropdowns (hidden ``_lists``):
          - Customer ← active customer names (A–Z), native Excel type-ahead
          - Segment  ← unique Industry Type Description values (A–Z)
          - Product  ← dependent on Segment via named ranges + INDIRECT/VLOOKUP
          - Reporting Month

        ``products_by_segment`` is preferred. Legacy ``products`` (flat list) still
        works by placing all codes under a single synthetic segment when no map given.
        """
        started = time.perf_counter()
        _ = distributors  # never prefill distributor header

        customer_values = self._unique_sorted(customers) or ["Sample Customer"]
        month_values = list(periods) if periods else [
            "January 2026",
            "February 2026",
            "March 2026",
            "April 2026",
            "May 2026",
            "June 2026",
            "July 2026",
            "August 2026",
            "September 2026",
            "October 2026",
            "November 2026",
            "December 2026",
        ]

        by_segment = self._resolve_products_by_segment(
            products_by_segment=products_by_segment,
            products=products,
            segments=segments,
        )

        warn_at = settings.template_list_warn_threshold
        total_products = sum(len(v) for v in by_segment.values())
        if len(customer_values) >= warn_at or total_products >= warn_at:
            logger.warning(
                "Large template master lists | customers={} | products={} | segments={} | threshold={}",
                len(customer_values),
                total_products,
                len(by_segment),
                warn_at,
            )

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = DISTRIBUTOR_TEMPLATE_SHEET
        lists_sheet = self.dropdowns.ensure_lists_sheet(workbook)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F5FA8")
        label_font = Font(bold=True, color="1F2937")
        note_font = Font(italic=True, color="6B7280", size=9)
        thin = Border(
            left=Side(style="thin", color="D0D5DD"),
            right=Side(style="thin", color="D0D5DD"),
            top=Side(style="thin", color="D0D5DD"),
            bottom=Side(style="thin", color="D0D5DD"),
        )

        detail_labels = [
            (1, "Name of Distributor"),
            (2, "Company Name"),
            (3, "Address"),
            (4, "Phone No"),
            (5, "Reporting Month"),
        ]
        for row_idx, label in detail_labels:
            cell = sheet.cell(row=row_idx, column=1, value=label)
            cell.font = label_font
            sheet.cell(row=row_idx, column=2, value=None)

        note = sheet.cell(
            row=6,
            column=1,
            value=(
                "Instructions: Select Segment first, then Product "
                "(Product list shows only codes for that Segment). "
                "After changing Segment, clear or re-select Product "
                "(mismatched Product cells highlight in red). "
                "Type in a dropdown cell to jump to matching values."
            ),
        )
        note.font = note_font
        sheet.merge_cells(start_row=6, start_column=1, end_row=6, end_column=7)

        table_header_row = 7
        for col_idx, header in enumerate(self.HEADERS, start=1):
            cell = sheet.cell(row=table_header_row, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin
            sheet.column_dimensions[get_column_letter(col_idx)].width = 22

        sheet.row_dimensions[table_header_row].height = 22
        sheet.freeze_panes = "A8"

        segment_values = sorted(by_segment.keys(), key=lambda s: s.casefold())

        cust_end = self.dropdowns.write_column_list(
            lists_sheet, column="A", title="Customers", values=customer_values
        )
        seg_end = self.dropdowns.write_column_list(
            lists_sheet, column="B", title="Segments", values=segment_values
        )
        month_end = self.dropdowns.write_column_list(
            lists_sheet, column="C", title="Reporting Months", values=month_values
        )

        ordered_segments, name_map = self.dropdowns.write_segment_product_columns(
            lists_sheet, products_by_segment=by_segment
        )
        self.dropdowns.write_segment_name_map(
            lists_sheet, name_map=name_map, segments=ordered_segments
        )

        self.dropdowns.register_named_range(
            workbook, name="CustomerList", sheet_title=lists_sheet.title, column="A", end_row=cust_end
        )
        self.dropdowns.register_named_range(
            workbook, name="SegmentList", sheet_title=lists_sheet.title, column="B", end_row=seg_end
        )
        self.dropdowns.register_named_range(
            workbook, name="MonthList", sheet_title=lists_sheet.title, column="C", end_row=month_end
        )

        # Customer / Segment / Month: flat lists (Excel native incremental search)
        self.dropdowns.add_list_validation(sheet, named_range="CustomerList", cells="B8:B1000")
        self.dropdowns.add_list_validation(sheet, named_range="SegmentList", cells="C8:C1000")
        # Product: dependent on Segment in column C
        self.dropdowns.add_dependent_product_validation(sheet, cells="D8:D1000")
        self.dropdowns.flag_invalid_segment_product(sheet, cells="D8:D1000")
        self.dropdowns.add_list_validation(sheet, named_range="MonthList", cells="B5")

        lists_sheet.protection.sheet = True
        lists_sheet.sheet_state = "hidden"

        for row_idx in range(8, 18):
            sheet.cell(row=row_idx, column=1, value=row_idx - 7)

        target = output_path or (Path(settings.download_dir) / DISTRIBUTOR_TEMPLATE_FILENAME)
        ensure_dir(target.parent)
        save_started = time.perf_counter()
        workbook.save(target)
        save_ms = round((time.perf_counter() - save_started) * 1000, 2)
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Generated distributor template at {} | customers={} products={} segments={} "
            "save_ms={} total_ms={}",
            target,
            len(customer_values),
            total_products,
            len(segment_values),
            save_ms,
            total_ms,
        )
        return target

    @staticmethod
    def _unique_sorted(values: Sequence[str]) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for raw in values:
            name = (raw or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
        out.sort(key=lambda s: s.casefold())
        return out

    def _resolve_products_by_segment(
        self,
        *,
        products_by_segment: Optional[Dict[str, Sequence[str]]],
        products: Optional[Sequence[str]],
        segments: Optional[Sequence[str]],
    ) -> Dict[str, List[str]]:
        if products_by_segment:
            result: Dict[str, List[str]] = {}
            for seg, codes in products_by_segment.items():
                segment = (seg or "").strip()
                if not segment:
                    continue
                cleaned = self._unique_sorted(list(codes))
                if cleaned:
                    result[segment] = cleaned
            if result:
                return result

        # Legacy flat product list → single bucket (tests / fallback only)
        flat = self._unique_sorted(list(products or [])) or ["SAMPLE-PRODUCT"]
        if segments:
            # Put all products under first provided segment for backward-compat tests
            primary = (list(segments)[0] or "GENERAL").strip() or "GENERAL"
            return {primary: flat}
        return {"GENERAL": flat}
