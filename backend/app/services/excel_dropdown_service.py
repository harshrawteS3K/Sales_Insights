"""Excel dropdown / named-range helpers for distributor templates."""

import time
from typing import Dict, List, Sequence, Tuple

from openpyxl.cell.cell import Cell
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.utils import get_column_letter

from app.core.logging import get_logger
from app.utils.excel_names import segment_range_name

logger = get_logger(__name__)


class ExcelDropdownService:
    """Apply hidden lookup lists, named ranges, and data validations."""

    LISTS_SHEET = "_lists"
    # Columns A–C reserved for Customers / Segments / Months
    # Column D = Segment→NamedRange map (for VLOOKUP)
    # Column E+ = per-segment product lists
    SEGMENT_MAP_COL = "D"
    FIRST_SEGMENT_PRODUCT_COL = 5  # column E

    def ensure_lists_sheet(self, workbook: Workbook) -> Worksheet:
        """Create or return the hidden lookup sheet."""
        if self.LISTS_SHEET in workbook.sheetnames:
            sheet = workbook[self.LISTS_SHEET]
        else:
            sheet = workbook.create_sheet(self.LISTS_SHEET)
        sheet.sheet_state = "hidden"
        sheet.protection.sheet = True
        return sheet

    def write_column_list(
        self,
        sheet: Worksheet,
        *,
        column: str,
        title: str,
        values: Sequence[str],
    ) -> int:
        """
        Write title + values in a column. Returns last data row (1-based).

        Uses direct cell map writes (identical workbook output to cell-by-cell API,
        lower overhead for large master lists).
        """
        from openpyxl.utils import column_index_from_string

        started = time.perf_counter()
        col_idx = column_index_from_string(column)
        cells = sheet._cells
        cells[(1, col_idx)] = Cell(sheet, row=1, column=col_idx, value=title)
        for idx, value in enumerate(values, start=2):
            cells[(idx, col_idx)] = Cell(sheet, row=idx, column=col_idx, value=value)
        end_row = max(len(values) + 1, 2)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Template list column written | column={} | title={} | rows={} | ms={}",
            column,
            title,
            len(values),
            elapsed_ms,
        )
        return end_row

    def write_segment_product_columns(
        self,
        sheet: Worksheet,
        *,
        products_by_segment: Dict[str, Sequence[str]],
    ) -> Tuple[List[str], Dict[str, str]]:
        """
        Write one column per segment (Industry Type Description) with product codes.

        Returns (ordered_segment_names, segment_display → named_range_key).
        """
        started = time.perf_counter()
        segments = sorted(products_by_segment.keys(), key=lambda s: s.casefold())
        name_map: Dict[str, str] = {}
        used_names: set[str] = set()
        cells = sheet._cells

        for offset, segment in enumerate(segments):
            col_idx = self.FIRST_SEGMENT_PRODUCT_COL + offset
            col_letter = get_column_letter(col_idx)
            range_name = segment_range_name(segment)
            # Guarantee uniqueness if two segments sanitize identically
            base = range_name
            suffix = 2
            while range_name in used_names:
                range_name = f"{base}_{suffix}"[:200]
                suffix += 1
            used_names.add(range_name)
            name_map[segment] = range_name

            products = list(products_by_segment.get(segment) or [])
            cells[(1, col_idx)] = Cell(sheet, row=1, column=col_idx, value=segment)
            for row_idx, code in enumerate(products, start=2):
                cells[(row_idx, col_idx)] = Cell(sheet, row=row_idx, column=col_idx, value=code)

            end_row = max(len(products) + 1, 2)
            self.register_named_range(
                sheet.parent,
                name=range_name,
                sheet_title=sheet.title,
                column=col_letter,
                end_row=end_row,
            )

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Segment product columns written | segments={} | total_products={} | ms={}",
            len(segments),
            sum(len(v) for v in products_by_segment.values()),
            elapsed_ms,
        )
        return segments, name_map

    def write_segment_name_map(
        self,
        sheet: Worksheet,
        *,
        name_map: Dict[str, str],
        segments: Sequence[str],
    ) -> int:
        """
        Write Segment → NamedRange key table in column D for VLOOKUP.

        D1 title, D2:E{n} not used — map is D=segment, E would collide.
        Layout: column D holds segment display names; named range keys go in a
        parallel column immediately after months… We use columns:
          D = segment (lookup key)
          and register a 2-col map starting at column index of SEGMENT_MAP.

        Actual layout: use columns far right of product cols is complex.
        Simpler: put map in columns A of a tiny area —
        Column D row1 = 'SegmentMapKey' unused.
        We write:
          col D = segment names (same order)
          We need two columns — use the last product col + 2.

        Fixed approach: write map at columns 1-indexed:
        Store map in columns ``map_col`` and ``map_col+1`` after all segment product cols.
        """
        # Place map immediately after product columns
        map_col = self.FIRST_SEGMENT_PRODUCT_COL + len(segments)
        key_col = map_col + 1
        cells = sheet._cells
        cells[(1, map_col)] = Cell(sheet, row=1, column=map_col, value="Segment")
        cells[(1, key_col)] = Cell(sheet, row=1, column=key_col, value="RangeKey")
        for idx, segment in enumerate(segments, start=2):
            cells[(idx, map_col)] = Cell(sheet, row=idx, column=map_col, value=segment)
            cells[(idx, key_col)] = Cell(
                sheet, row=idx, column=key_col, value=name_map[segment]
            )
        end_row = max(len(segments) + 1, 2)
        map_start = get_column_letter(map_col)
        map_end = get_column_letter(key_col)
        # Workbook-scoped named range covering both columns
        try:
            del sheet.parent.defined_names["SegmentMap"]
        except KeyError:
            pass
        attr = f"'{sheet.title}'!${map_start}$2:${map_end}${end_row}"
        sheet.parent.defined_names.add(DefinedName(name="SegmentMap", attr_text=attr))
        return end_row

    def register_named_range(
        self,
        workbook: Workbook,
        *,
        name: str,
        sheet_title: str,
        column: str,
        end_row: int,
    ) -> None:
        """Register a workbook-scoped named range for dropdown formulas."""
        try:
            del workbook.defined_names[name]
        except KeyError:
            pass
        attr = f"'{sheet_title}'!${column}$2:${column}${end_row}"
        workbook.defined_names.add(DefinedName(name=name, attr_text=attr))

    def add_list_validation(
        self,
        sheet: Worksheet,
        *,
        named_range: str,
        cells: str,
    ) -> DataValidation:
        """Attach a list data-validation to ``cells`` using a named range."""
        dv = DataValidation(
            type="list",
            formula1=f"={named_range}",
            allow_blank=True,
            showDropDown=False,  # False = show dropdown arrow in Excel
        )
        dv.error = "Please select a value from the list"
        dv.errorTitle = "Invalid selection"
        dv.prompt = "Select from master data"
        dv.promptTitle = "Master Data"
        dv.add(cells)
        sheet.add_data_validation(dv)
        return dv

    def add_dependent_product_validation(
        self,
        sheet: Worksheet,
        *,
        cells: str = "D8:D1000",
        segment_cell_relative: str = "$C8",
    ) -> DataValidation:
        """
        Product dropdown filtered by Segment via INDIRECT(VLOOKUP(...)).

        When Segment (col C) changes, Excel re-evaluates the list for that row.
        Native type-to-search still works within the filtered list.

        Excel cannot auto-clear Product without VBA. We:
          - use stop-style validation so wrong-segment products are rejected on edit
          - apply conditional formatting (see ``flag_invalid_segment_product``) so
            stale Product values highlight after Segment changes
        """
        formula = f'=INDIRECT(VLOOKUP({segment_cell_relative},SegmentMap,2,FALSE))'
        dv = DataValidation(
            type="list",
            formula1=formula,
            allow_blank=True,
            showDropDown=False,
            showErrorMessage=True,
            showInputMessage=True,
            errorStyle="stop",
        )
        dv.error = (
            "Product must belong to the selected Segment. "
            "Clear or re-select Product after changing Segment."
        )
        dv.errorTitle = "Invalid Product"
        dv.prompt = "Select Segment first, then Product (type to search within Segment)"
        dv.promptTitle = "Segment → Product"
        dv.add(cells)
        sheet.add_data_validation(dv)
        return dv

    def flag_invalid_segment_product(
        self,
        sheet: Worksheet,
        *,
        cells: str = "D8:D1000",
    ) -> None:
        """
        Highlight Product cells that do not belong to the row's Segment.

        Acts as the production-safe substitute for auto-clear (no macros):
        after Segment changes, a mismatched Product turns red until re-selected.
        """
        from openpyxl.formatting.rule import FormulaRule
        from openpyxl.styles import PatternFill

        fill = PatternFill(start_color="FECACA", end_color="FECACA", fill_type="solid")
        # Stale / wrong-segment product, or product with no segment
        formula = (
            'OR('
            'AND($C8="",$D8<>""),'
            'AND($C8<>"",$D8<>"",'
            'ISERROR(MATCH($D8,INDIRECT(VLOOKUP($C8,SegmentMap,2,FALSE)),0)))'
            ')'
        )
        sheet.conditional_formatting.add(
            cells,
            FormulaRule(formula=[formula], fill=fill),
        )
