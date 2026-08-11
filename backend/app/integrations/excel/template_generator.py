"""Distributor Excel template generator — quarterly APCOTEX layout."""

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

QUARTER_GUIDANCE = (
    "Note: Q1 = April – June  |  Q2 = July – September  |  "
    "Q3 = October – December  |  Q4 = January – March"
)

CUSTOMER_LIST_SHEET = "CustomerList"


class ExcelTemplateGenerator:
    """Generate quarterly distributor sales Excel templates with Segment→Product dropdowns."""

    HEADERS = [
        "Sr. No.",
        "Customer Name",
        "Segment",
        "Product",
        "Sales Quantity",
    ]

    def __init__(self, dropdowns: Optional[ExcelDropdownService] = None) -> None:
        self.dropdowns = dropdowns or ExcelDropdownService()

    def generate(
        self,
        *,
        customers: Optional[Sequence[str]] = None,
        products_by_segment: Optional[Dict[str, Sequence[str]]] = None,
        products: Optional[Sequence[str]] = None,
        segments: Optional[Sequence[str]] = None,
        distributors: Optional[Sequence[str]] = None,
        output_path: Optional[Path] = None,
        periods: Optional[Sequence[str]] = None,
        mode: str = "generic",
        contact_person: Optional[str] = None,
        company_name: Optional[str] = None,
        reporting_quarter: Optional[str] = None,
    ) -> Path:
        """
        Create a quarterly distributor sales template.

        Mode ``generic``: Customer Name free text.
        Mode ``distributor``: Customer Name dropdown from prior-quarter customers.
        """
        started = time.perf_counter()
        _ = distributors
        _ = periods
        mode_key = (mode or "generic").strip().lower()
        distributor_mode = mode_key in {"distributor", "distributor_specific", "specific"}
        # Preserve previous-quarter-first order from the service for distributor mode.
        customer_values = (
            self._unique_preserve_order(list(customers or []))
            if distributor_mode
            else self._unique_sorted(list(customers or []))
        )

        by_segment = self._resolve_products_by_segment(
            products_by_segment=products_by_segment,
            products=products,
            segments=segments,
        )

        warn_at = settings.template_list_warn_threshold
        total_products = sum(len(v) for v in by_segment.values())
        if total_products >= warn_at:
            logger.warning(
                "Large template product lists | products={} | segments={} | threshold={}",
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
        guidance_font = Font(bold=False, color="1E3A5F", size=9)
        guidance_fill = PatternFill("solid", fgColor="E8F1FB")
        thin = Border(
            left=Side(style="thin", color="D0D5DD"),
            right=Side(style="thin", color="D0D5DD"),
            top=Side(style="thin", color="D0D5DD"),
            bottom=Side(style="thin", color="D0D5DD"),
        )

        detail_labels = [
            (1, "Name of Person"),
            (2, "Company Name"),
            (3, "Reporting Quarter"),
        ]
        for row_idx, label in detail_labels:
            cell = sheet.cell(row=row_idx, column=1, value=label)
            cell.font = label_font

        sheet.cell(row=1, column=2, value=(contact_person or None))
        sheet.cell(row=2, column=2, value=(company_name or None))
        sheet.cell(row=3, column=2, value=(reporting_quarter or None))
        sheet.cell(row=3, column=2).number_format = "@"

        guidance = sheet.cell(row=4, column=1, value=QUARTER_GUIDANCE)
        guidance.font = guidance_font
        guidance.fill = guidance_fill
        guidance.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.merge_cells(start_row=4, start_column=1, end_row=4, end_column=5)
        sheet.row_dimensions[4].height = 28
        for col in range(1, 6):
            sheet.cell(row=4, column=col).fill = guidance_fill

        if distributor_mode:
            instruction = (
                "Instructions: Select Customer Name from the dropdown "
                "(all customers previously submitted by this distributor). "
                "Enter Reporting Quarter as Q1/Q2/Q3/Q4 YYYY (see note above). "
                "Select Segment first, then Product "
                "(list shows only codes for that Segment). "
                "After changing Segment, clear or re-select Product "
                "(mismatched Product cells highlight in red)."
            )
        else:
            instruction = (
                "Instructions: Enter Customer Name as free text. "
                "Enter Reporting Quarter as Q1/Q2/Q3/Q4 YYYY (see note above). "
                "Select Segment first, then Product "
                "(list shows only codes for that Segment). "
                "After changing Segment, clear or re-select Product "
                "(mismatched Product cells highlight in red)."
            )
        note = sheet.cell(row=5, column=1, value=instruction)
        note.font = note_font
        sheet.merge_cells(start_row=5, start_column=1, end_row=5, end_column=5)

        table_header_row = 6
        for col_idx, header in enumerate(self.HEADERS, start=1):
            cell = sheet.cell(row=table_header_row, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin
            sheet.column_dimensions[get_column_letter(col_idx)].width = 24

        sheet.row_dimensions[table_header_row].height = 22
        sheet.freeze_panes = "A7"

        segment_values = sorted(by_segment.keys(), key=lambda s: s.casefold())

        seg_end = self.dropdowns.write_column_list(
            lists_sheet, column="B", title="Segments", values=segment_values
        )

        ordered_segments, name_map = self.dropdowns.write_segment_product_columns(
            lists_sheet, products_by_segment=by_segment
        )
        self.dropdowns.write_segment_name_map(
            lists_sheet, name_map=name_map, segments=ordered_segments
        )

        self.dropdowns.register_named_range(
            workbook, name="SegmentList", sheet_title=lists_sheet.title, column="B", end_row=seg_end
        )

        data_start = 7
        self.dropdowns.add_list_validation(
            sheet, named_range="SegmentList", cells=f"C{data_start}:C1000"
        )
        self.dropdowns.add_dependent_product_validation(
            sheet,
            cells=f"D{data_start}:D1000",
            segment_cell_relative=f"$C{data_start}",
        )
        self.dropdowns.flag_invalid_segment_product(
            sheet,
            cells=f"D{data_start}:D1000",
            segment_col="$C",
            product_col="$D",
            start_row=data_start,
        )

        if distributor_mode:
            logger.info(
                "Distributor template customers | count={} | values={}",
                len(customer_values),
                customer_values[:20],
            )
            customer_sheet = workbook.create_sheet(CUSTOMER_LIST_SHEET)
            cust_end = self.dropdowns.write_column_list(
                customer_sheet,
                column="A",
                title="Customers",
                values=customer_values or ["(No mapped customers yet)"],
            )
            self.dropdowns.register_named_range(
                workbook,
                name="DistributorCustomers",
                sheet_title=CUSTOMER_LIST_SHEET,
                column="A",
                end_row=cust_end,
            )
            if customer_values:
                self.dropdowns.add_list_validation(
                    sheet,
                    named_range="DistributorCustomers",
                    cells=f"B{data_start}:B1000",
                )
                logger.info(
                    "Customer Name data validation attached | range=B{}:B1000 | named_range=DistributorCustomers",
                    data_start,
                )
            customer_sheet.protection.sheet = True
            customer_sheet.sheet_state = "hidden"

        lists_sheet.protection.sheet = True
        lists_sheet.sheet_state = "hidden"

        for row_idx in range(data_start, data_start + 10):
            sheet.cell(row=row_idx, column=1, value=row_idx - (data_start - 1))

        target = output_path or (Path(settings.download_dir) / DISTRIBUTOR_TEMPLATE_FILENAME)
        ensure_dir(target.parent)
        save_started = time.perf_counter()
        workbook.save(target)
        save_ms = round((time.perf_counter() - save_started) * 1000, 2)
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Generated quarterly distributor template at {} | mode={} | products={} "
            "segments={} customers={} save_ms={} total_ms={}",
            target,
            "distributor" if distributor_mode else "generic",
            total_products,
            len(segment_values),
            len(customer_values),
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

    @staticmethod
    def _unique_preserve_order(values: Sequence[str]) -> List[str]:
        """De-dupe while keeping caller order (previous-quarter-first lists)."""
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

        flat = self._unique_sorted(list(products or [])) or ["SAMPLE-PRODUCT"]
        if segments:
            primary = (list(segments)[0] or "GENERAL").strip() or "GENERAL"
            return {primary: flat}
        return {"GENERAL": flat}
