"""Distributor Excel template generator matching the official APCOTEX layout."""

import time
from pathlib import Path
from typing import List, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.constants import (
    DEFAULT_SEGMENTS,
    DISTRIBUTOR_TEMPLATE_FILENAME,
    DISTRIBUTOR_TEMPLATE_SHEET,
)
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

        Customer and Product columns use master-data dropdowns (hidden `_lists` sheet).
        """
        started = time.perf_counter()
        segment_values = list(segments) if segments is not None else list(DEFAULT_SEGMENTS)
        customer_values = list(customers) if customers else ["Sample Customer"]
        product_values = list(products) if products else ["SAMPLE-PRODUCT"]
        distributor_values = list(distributors) if distributors else []
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

        warn_at = settings.template_list_warn_threshold
        if len(customer_values) >= warn_at or len(product_values) >= warn_at:
            logger.warning(
                "Large template master lists | customers={} | products={} | threshold={}",
                len(customer_values),
                len(product_values),
                warn_at,
            )

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = DISTRIBUTOR_TEMPLATE_SHEET
        lists_sheet = self.dropdowns.ensure_lists_sheet(workbook)

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
        sheet.freeze_panes = "A8"

        cust_end = self.dropdowns.write_column_list(
            lists_sheet, column="A", title="Customers", values=customer_values
        )
        prod_end = self.dropdowns.write_column_list(
            lists_sheet, column="B", title="Products", values=product_values
        )
        seg_end = self.dropdowns.write_column_list(
            lists_sheet, column="C", title="Segments", values=segment_values
        )
        month_end = self.dropdowns.write_column_list(
            lists_sheet, column="D", title="Reporting Months", values=month_values
        )

        self.dropdowns.register_named_range(
            workbook, name="CustomerList", sheet_title=lists_sheet.title, column="A", end_row=cust_end
        )
        self.dropdowns.register_named_range(
            workbook, name="ProductList", sheet_title=lists_sheet.title, column="B", end_row=prod_end
        )
        self.dropdowns.register_named_range(
            workbook, name="SegmentList", sheet_title=lists_sheet.title, column="C", end_row=seg_end
        )
        self.dropdowns.register_named_range(
            workbook, name="MonthList", sheet_title=lists_sheet.title, column="D", end_row=month_end
        )

        # Name of Customer = col B, Product = col D
        self.dropdowns.add_list_validation(sheet, named_range="CustomerList", cells="B8:B1000")
        self.dropdowns.add_list_validation(sheet, named_range="SegmentList", cells="C8:C1000")
        self.dropdowns.add_list_validation(sheet, named_range="ProductList", cells="D8:D1000")
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
            len(product_values),
            len(segment_values),
            save_ms,
            total_ms,
        )
        return target
