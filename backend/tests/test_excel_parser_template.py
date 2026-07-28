"""Regression tests for template-driven APCOTEX Excel parser."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.exceptions import ExcelProcessingError
from app.integrations.excel.headers import normalize_header
from app.integrations.excel.parser import ExcelParserService
from tests.workbook_helpers import build_official_workbook


@pytest.fixture
def parser() -> ExcelParserService:
    return ExcelParserService()


def _save(wb: Workbook, path: Path) -> Path:
    wb.save(path)
    return path


def test_normalize_header_variants():
    assert normalize_header("Sr. No.") == "sr no"
    assert normalize_header("Name of Customer") == "name of customer"
    assert normalize_header("Customer_Name") == "customer name"
    assert normalize_header("customer-name") == "customer name"
    assert normalize_header("CUSTOMER NAME") == "customer name"
    assert normalize_header("Reporting Month") == "reporting month"


def test_official_apcotex_template(parser: ExcelParserService, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "official.xlsx",
        distributor="Navneet Goel",
        reporting_month="July 2026",
        company="M/S PUNEET DYES",
        address="Shop no. 2",
        phone="0180-2646741",
        include_stock=True,
        rows=[
            (1, "M/S AKS RUGS CO.", "Carpet", "APCOTEX CB 4600", 3300, 2000, 20),
            (2, "M/S BETA CO.", "Carpet", "APCOTEX CB 300", 100, 2000, 20),
        ],
    )
    result = parser.parse_sales_report(path)

    assert result.mapping_strategy == "official_template"
    assert result.template_name == "Official APCOTEX Template"
    assert result.imported_rows == 2
    assert result.incomplete_rows == 0
    assert result.quality_score >= 95
    assert result.reporting_month == "July 2026"
    assert result.distributor_details["name"] == "Navneet Goel"
    assert result.distributor_details["phone"] == "0180-2646741"
    assert result.rows[0].opening_stock == 2000
    assert result.rows[0].closing_stock == 20
    assert result.rows[0].period == "July 2026"


def test_official_without_stock_columns(parser: ExcelParserService, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "no_stock.xlsx",
        distributor="Dist A",
        reporting_month="June 2026",
        include_stock=False,
        rows=[(1, "Cust A", "Carpet", "CB 300", 10)],
    )
    result = parser.parse_sales_report(path)
    assert result.imported_rows == 1
    assert result.rows[0].opening_stock is None
    assert result.rows[0].closing_stock is None


def test_legacy_period_column_fallback(parser: ExcelParserService, tmp_path: Path):
    """Old Excel with Period column and no Reporting Month header still works."""
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Name of Distributor"
    ws["B1"] = "Legacy Dist"
    ws["A2"] = "Company Name"
    ws["B2"] = "Co"
    for i, h in enumerate(
        ["Sr. No.", "Name of Customer", "Segment", "Product", "Quantity", "Period"], 1
    ):
        ws.cell(9, i, h)
    for c, v in enumerate([1, "Cust A", "Carpet", "CB 300", 10, "Q2 FY26"], 1):
        ws.cell(10, c, v)
    result = parser.parse_sales_report(_save(wb, tmp_path / "legacy_period.xlsx"))
    assert result.imported_rows == 1
    assert result.reporting_month == "Q2 FY26"


def test_skips_invalid_rows_imports_valid(parser: ExcelParserService, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "skip.xlsx",
        distributor="Dist",
        reporting_month="May 2026",
        include_stock=False,
        rows=[
            (1, "Good", "Carpet", "P1", 10),
            (2, "", "Carpet", "P1", 10),
        ],
    )
    result = parser.parse_sales_report(path)
    assert result.expected_rows == 2
    assert result.imported_rows == 1
    assert result.incomplete_rows == 1
    assert any("Missing Customer" in e for e in result.row_errors)


def test_legacy_customer_name_fallback(parser: ExcelParserService, tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Distributor Name"
    ws["B1"] = "Legacy Dist"
    ws["A2"] = "Reporting Month"
    ws["B2"] = "Q1 FY26"
    for i, h in enumerate(
        ["Sr No", "Customer Name", "Segment", "Product", "Quantity"], 1
    ):
        ws.cell(6, i, h)
    for c, v in enumerate([1, "Cust A", "Tyre", "CB 300", 10], 1):
        ws.cell(7, c, v)

    result = parser.parse_sales_report(_save(wb, tmp_path / "legacy.xlsx"))
    assert result.imported_rows == 1
    assert result.reporting_month == "Q1 FY26"


def test_header_mismatch_fails_fast(parser: ExcelParserService, tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    for i, h in enumerate(["Foo", "Bar", "Baz"], 1):
        ws.cell(1, i, h)
    ws.cell(2, 1, "x")

    with pytest.raises(ExcelProcessingError) as exc:
        parser.parse_sales_report(_save(wb, tmp_path / "bad.xlsx"))
    assert "validation failed" in str(exc.value).lower() or "Missing" in str(exc.value)


def test_missing_reporting_month_fails(parser: ExcelParserService, tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Name of Distributor"
    ws["B1"] = "Dist"
    for i, h in enumerate(
        ["Sr. No.", "Name of Customer", "Segment", "Product", "Quantity"], 1
    ):
        ws.cell(9, i, h)
    for c, v in enumerate([1, "Cust", "Carpet", "P1", 10], 1):
        ws.cell(10, c, v)
    with pytest.raises(ExcelProcessingError) as exc:
        parser.parse_sales_report(_save(wb, tmp_path / "no_month.xlsx"))
    assert "Reporting Month" in str(exc.value)
