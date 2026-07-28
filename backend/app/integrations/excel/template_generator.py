"""Distributor Excel template generator matching the official APCOTEX layout."""

from pathlib import Path
from typing import List, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.constants import (
    DEFAULT_SEGMENTS,
    DISTRIBUTOR_TEMPLATE_FILENAME,
    DISTRIBUTOR_TEMPLATE_SHEET,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.files import ensure_dir

logger = get_logger(__name__)


class ExcelTemplateGenerator:
    """Generate distributor sales Excel templates with dropdown lists."""

    # Official sales table (Reporting Month is in the Distributor Details block)
    HEADERS = [
        "Sr. No.",
        "Name of Customer",
        "Segment",
        "Product",
        "Quantity",
        "Opening Stock",
        "Closing Stock",
    ]

    def generate(
        self,
        *,
        customers: Sequence[str],
        products: Sequence[str],
        segments: Optional[Sequence[str]] = None,
        distributors: Optional[Sequence[str]] = None,
        output_path: Optional[Path] = None,
        periods: Optional[Sequence[str]] = None,
    ) -> Path:
        """
        Create a distributor sales template workbook.

        Layout:
          Rows 1–5  Distributor Details (Name, Company, Address, Phone, Reporting Month)
          Row 7     Sales table headers
          Row 8+    Sales data
        """
        segment_values = list(segments or DEFAULT_SEGMENTS)
        customer_values = list(customers) or ["Sample Customer"]
        product_values = list(products) or ["CB 300"]
        distributor_values = list(distributors or [])
        month_values = list(
            periods
            or [
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
        )

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = DISTRIBUTOR_TEMPLATE_SHEET
        lists_sheet = workbook.create_sheet("_lists")

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F5FA8")
        label_font = Font(bold=True, color="1F2937")
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
            sheet.cell(row=row_idx, column=2, value="")

        if distributor_values:
            sheet.cell(row=1, column=2, value=distributor_values[0])
        if month_values:
            sheet.cell(row=5, column=2, value=month_values[0])

        table_header_row = 7
        for col_idx, header in enumerate(self.HEADERS, start=1):
            cell = sheet.cell(row=table_header_row, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin
            sheet.column_dimensions[get_column_letter(col_idx)].width = 22

        sheet.row_dimensions[table_header_row].height = 22

        self._write_list(lists_sheet, "A", "Customers", customer_values)
        self._write_list(lists_sheet, "B", "Products", product_values)
        self._write_list(lists_sheet, "C", "Segments", segment_values)
        self._write_list(lists_sheet, "D", "Reporting Months", month_values)

        customer_dv = DataValidation(
            type="list",
            formula1=f"=_lists!$A$2:$A${len(customer_values) + 1}",
            allow_blank=True,
        )
        product_dv = DataValidation(
            type="list",
            formula1=f"=_lists!$B$2:$B${len(product_values) + 1}",
            allow_blank=True,
        )
        segment_dv = DataValidation(
            type="list",
            formula1=f"=_lists!$C$2:$C${len(segment_values) + 1}",
            allow_blank=True,
        )
        month_dv = DataValidation(
            type="list",
            formula1=f"=_lists!$D$2:$D${len(month_values) + 1}",
            allow_blank=True,
        )

        customer_dv.add("B8:B1000")
        product_dv.add("D8:D1000")
        segment_dv.add("C8:C1000")
        month_dv.add("B5")

        sheet.add_data_validation(customer_dv)
        sheet.add_data_validation(product_dv)
        sheet.add_data_validation(segment_dv)
        sheet.add_data_validation(month_dv)

        lists_sheet.sheet_state = "hidden"

        for row_idx in range(8, 18):
            sheet.cell(row=row_idx, column=1, value=row_idx - 7)

        target = output_path or (Path(settings.download_dir) / DISTRIBUTOR_TEMPLATE_FILENAME)
        ensure_dir(target.parent)
        workbook.save(target)
        logger.info(
            "Generated distributor template at {} | customers={} products={} segments={}",
            target,
            len(customer_values),
            len(product_values),
            len(segment_values),
        )
        return target

    @staticmethod
    def _write_list(sheet, column: str, title: str, values: List[str]) -> None:
        sheet[f"{column}1"] = title
        sheet[f"{column}1"].font = Font(bold=True)
        for idx, value in enumerate(values, start=2):
            sheet[f"{column}{idx}"] = value
