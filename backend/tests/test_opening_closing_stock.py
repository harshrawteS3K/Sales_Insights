"""Quarterly template: Opening/Closing Stock removed from parse & persist path."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.integrations.excel.parser import ExcelParserService
from app.utils.quantity import parse_optional_stock
from tests.workbook_helpers import build_official_workbook


@pytest.fixture
def parser() -> ExcelParserService:
    return ExcelParserService()


def test_parse_optional_stock_helper_still_exists_for_legacy_utils():
    """Helper retained for utility tests; parser no longer maps stock columns."""
    assert parse_optional_stock(None) is None
    assert parse_optional_stock("") is None
    assert parse_optional_stock(0) == Decimal("0")


def test_quarterly_template_ignores_legacy_stock_columns(
    parser: ExcelParserService, tmp_path: Path
):
    path = build_official_workbook(
        tmp_path / "with_stock.xlsx",
        distributor="John Doe",
        reporting_month="Q3 2026",
        include_stock=True,
        rows=[(1, "Cust A", "Carpet", "APCOTEX CB 4600", 3300, 2000, 20)],
    )
    result = parser.parse_sales_report(path)
    assert result.imported_rows == 1
    assert result.reporting_month == "Q3 2026"
    assert result.rows[0].quantity == Decimal("3300")
    assert not hasattr(result.rows[0], "opening_stock") or getattr(
        result.rows[0], "opening_stock", None
    ) is None


def test_quarterly_template_parses_four_columns(
    parser: ExcelParserService, tmp_path: Path
):
    path = build_official_workbook(
        tmp_path / "q.xlsx",
        distributor="Jane Person",
        reporting_month="Q1 2026",
        include_stock=False,
        rows=[(1, "Free Text Customer", "Carpet", "FG-001", 100)],
    )
    result = parser.parse_sales_report(path)
    assert result.mapping_strategy == "official_template"
    assert result.imported_rows == 1
    assert result.rows[0].customer_name == "Free Text Customer"
    assert result.rows[0].product == "FG-001"
    assert result.rows[0].quantity == Decimal("100")
    assert result.reporting_month == "Q1 2026"


def test_sales_quantity_must_be_positive(parser: ExcelParserService, tmp_path: Path):
    from app.exceptions import ExcelProcessingError

    path = build_official_workbook(
        tmp_path / "zero.xlsx",
        distributor="Person",
        reporting_month="Q2 2026",
        rows=[(1, "Cust", "Carpet", "P1", 0)],
    )
    with pytest.raises(ExcelProcessingError):
        parser.parse_sales_report(path)
