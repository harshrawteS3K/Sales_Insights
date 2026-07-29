"""Excel dropdown / named-range helpers for distributor templates."""

import time
from typing import Sequence

from openpyxl.cell.cell import Cell
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from app.core.logging import get_logger

logger = get_logger(__name__)


class ExcelDropdownService:
    """Apply hidden lookup lists, named ranges, and data validations."""

    LISTS_SHEET = "_lists"

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
        # Remove existing definition with same name if present
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
