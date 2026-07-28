"""Tests for Opening Stock / Closing Stock with report-level Reporting Month."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database.session import SessionLocal
from app.exceptions import ExcelProcessingError
from app.integrations.excel.parser import ExcelParserService
from app.models.sales_record import SalesRecord
from app.services.report_service import ReportService
from app.utils.quantity import parse_optional_stock
from tests.workbook_helpers import build_official_workbook


@pytest.fixture
def parser() -> ExcelParserService:
    return ExcelParserService()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_parse_optional_stock_rules():
    assert parse_optional_stock(None) is None
    assert parse_optional_stock("") is None
    assert parse_optional_stock(0) == Decimal("0")
    assert parse_optional_stock("2,000") == Decimal("2000")
    with pytest.raises(ValueError):
        parse_optional_stock(-1)
    with pytest.raises(ValueError):
        parse_optional_stock("not-a-number")


def test_scenario1_old_stockless_template(parser: ExcelParserService, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "old.xlsx",
        distributor="Old Dist",
        reporting_month="July 2026",
        include_stock=False,
        rows=[(1, "Cust A", "Carpet", "APCOTEX CB 4600", 100)],
    )
    result = parser.parse_sales_report(path)
    assert result.imported_rows == 1
    assert result.rows[0].opening_stock is None
    assert result.rows[0].closing_stock is None
    assert result.reporting_month == "July 2026"


def test_scenario2_new_template_stores_stock(parser: ExcelParserService, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "new.xlsx",
        distributor="New Dist",
        reporting_month="July 2026",
        rows=[(1, "M/S AKS RUGS CO.", "Carpet", "APCOTEX CB 4600", 3300, 2000, 20)],
    )
    result = parser.parse_sales_report(path)
    assert result.mapping_strategy == "official_template"
    assert result.imported_rows == 1
    assert result.rows[0].opening_stock == Decimal("2000")
    assert result.rows[0].closing_stock == Decimal("20")
    assert result.rows[0].quantity == Decimal("3300")


def test_scenario3_blank_stock_null(parser: ExcelParserService, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "blank.xlsx",
        distributor="Blank Dist",
        reporting_month="July 2026",
        rows=[(1, "Cust", "Carpet", "P1", 10, None, None)],
    )
    result = parser.parse_sales_report(path)
    assert result.imported_rows == 1
    assert result.rows[0].opening_stock is None
    assert result.rows[0].closing_stock is None


def test_scenario4_invalid_stock_validation(parser: ExcelParserService, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "bad_stock.xlsx",
        distributor="Bad Dist",
        reporting_month="July 2026",
        rows=[(1, "Cust", "Carpet", "P1", 10, "abc", "xyz")],
    )
    with pytest.raises(ExcelProcessingError) as exc:
        parser.parse_sales_report(path)
    details = exc.value.details or {}
    errors = details.get("errors") or []
    assert any("Opening Stock" in e or "Closing Stock" in e for e in errors)


def test_scenario2_persist_and_api_shape(db, tmp_path: Path):
    dist = f"Stock Dist {uuid4().hex[:8]}"
    path = build_official_workbook(
        tmp_path / "persist.xlsx",
        distributor=dist,
        reporting_month="August 2099",
        rows=[(1, "Cust", "Carpet", "APCOTEX CB 4600", 3300, 1500, 40)],
    )
    service = ReportService(db)
    report, inserted, dup, _ = service.ingest_excel(path, actor="test")
    assert inserted == 1 and dup is False
    assert report.reporting_month == "August 2099"

    sales = list(
        db.scalars(
            select(SalesRecord).where(
                SalesRecord.report_id == report.id,
                SalesRecord.is_deleted.is_(False),
            )
        ).all()
    )
    assert len(sales) == 1
    assert sales[0].opening_stock == Decimal("1500")
    assert sales[0].closing_stock == Decimal("40")

    frontend = service.consolidated_records(limit=5000)
    match = [r for r in frontend if r.reportId == report.id]
    assert match
    assert match[0].openingStock == "1,500"
    assert match[0].closingStock == "40"
    assert match[0].reportingMonth == "August 2099"
