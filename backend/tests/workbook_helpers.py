"""Helpers to build official APCOTEX sales workbooks for tests."""

from pathlib import Path
from typing import Optional, Sequence

from openpyxl import Workbook


def build_official_workbook(
    path: Path,
    *,
    distributor: str,
    reporting_month: str,
    rows: Sequence[tuple],
    include_stock: bool = True,
    legacy_period_column: bool = False,
    company: Optional[str] = None,
    address: str = "Addr",
    phone: str = "999",
) -> Path:
    """
    Build the finalized official template.

    Sales columns: Sr No, Customer, Segment, Product, Quantity [, Opening, Closing]
    Reporting Month is in Distributor Details (not a sales column).

    Company defaults to the distributor name so tests that use unique
    representative names also get unique company identity unless overridden.
    """
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Name of Distributor"
    ws["B1"] = distributor
    ws["A2"] = "Company Name"
    ws["B2"] = company if company is not None else distributor
    ws["A3"] = "Address"
    ws["B3"] = address
    ws["A4"] = "Phone No"
    ws["B4"] = phone
    ws["A5"] = "Reporting Month"
    ws["B5"] = reporting_month

    headers = ["Sr. No.", "Name of Customer", "Segment", "Product", "Quantity"]
    if include_stock:
        headers.extend(["Opening Stock", "Closing Stock"])
    if legacy_period_column:
        headers.append("Period")

    for i, h in enumerate(headers, 1):
        ws.cell(9, i, h)

    for r, row in enumerate(rows, 1):
        for c, v in enumerate(row, 1):
            ws.cell(9 + r, c, v)

    wb.save(path)
    return path
