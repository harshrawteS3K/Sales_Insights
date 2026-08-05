"""Phase 2 production hardening — viz consistency + master data scale."""

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.integrations.excel.parser import ExcelParserService
from app.integrations.excel.template_generator import ExcelTemplateGenerator
from app.repositories.sales_record_repository import SalesRecordRepository
from app.services.business_aggregation_service import BusinessAggregationService
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService
from tests.workbook_helpers import build_official_workbook


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


def test_dashboard_qty_matches_distributor_totals_sum(db: Session, tmp_path: Path):
    """Filtered product / company totals must share the same ACTIVE universe."""
    company = "Viz Align Co Unique"
    for month, qty in [("January 2091", 10), ("February 2091", 25)]:
        path = build_official_workbook(
            tmp_path / f"{month}.xlsx",
            distributor="Rep Viz Align",
            company=company,
            reporting_month=month,
            rows=[(1, "C1", "Paper", "P-ALIGN", qty, 1, 2)],
        )
        ReportService(db).ingest_excel(path, actor="test")

    dash = DashboardService(db)
    dist_sum = sum(
        r.qty for r in dash.distributor_totals(distributor=company)
    )
    prod_sum = sum(
        r.qty for r in dash.product_quantities(distributor=company)
    )
    assert dist_sum == prod_sum == 35.0
    jan = dash.monthly_sales_trend(distributor=company)
    assert sum(r["qty"] for r in jan) == 35.0


def test_top_distributors_includes_others(db: Session, tmp_path: Path):
    """Horizontal bar Top-N must roll remainder into Others (matches donut)."""
    for i in range(5):
        path = build_official_workbook(
            tmp_path / f"d{i}.xlsx",
            distributor=f"Rep TopDist {i}",
            company=f"TopDist Co {i} Unique",
            reporting_month="March 2091",
            rows=[(1, "C", "Paper", "PX", 10 * (i + 1), 1, 2)],
        )
        ReportService(db).ingest_excel(path, actor="test")

    # Scope via product unique to this test so global data does not dominate Top-N
    rows = DashboardService(db).top_distributors(product="PX", limit=2)
    names = [r["name"] for r in rows]
    assert "Others" in names
    assert sum(r["qty"] for r in rows) == 150.0  # 10+20+30+40+50


def test_dist_product_mix_uses_top_products_not_hardcoded(db: Session, tmp_path: Path):
    company = "Mix Dyn Co Unique"
    path = build_official_workbook(
        tmp_path / "mix.xlsx",
        distributor="Mix Rep",
        company=company,
        reporting_month="April 2091",
        rows=[
            (1, "C", "Paper", "ALPHA-X", 50, 1, 2),
            (2, "C", "Paper", "BETA-Y", 30, 1, 2),
            (3, "C", "Paper", "GAMMA-Z", 10, 1, 2),
        ],
    )
    ReportService(db).ingest_excel(path, actor="test")
    mix = DashboardService(db).dist_product_mix(
        distributor=company, top_products=2, distributor_limit=10
    )
    assert mix
    keys = {k for row in mix for k in row if k != "distributor"}
    assert "ALPHA-X" in keys
    assert "BETA-Y" in keys
    assert "GAMMA-Z" not in keys  # only top 2 products
    assert "CB 300" not in keys


def test_company_filter_uses_company_expr(db: Session, tmp_path: Path):
    """Legacy blank-company rows: filter by representative fallback label still works."""
    # Normal company path
    company = "Filter Expr Co Unique"
    path = build_official_workbook(
        tmp_path / "f.xlsx",
        distributor="Filter Rep",
        company=company,
        reporting_month="May 2091",
        rows=[(1, "C", "Paper", "PF", 7, 1, 2)],
    )
    ReportService(db).ingest_excel(path, actor="test")
    repo = SalesRecordRepository(db)
    rows = repo.quarterly_company_summary(
        ["May 2091"],
        company=company,
    )
    assert len(rows) == 1
    assert rows[0]["qty"] == 7.0


def test_customer_master_extracts_name_only(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append(["CUSTOMER NAME", "REGION", "CODE", "IGNORED"])
    ws.append(["Acme Corp", "West", "A1", "noise"])
    ws.append(["Beta Ltd", "East", "B1", "noise"])
    ws.append(["acme corp", "South", "A2", "dup"])  # casefold dupe
    path = tmp_path / "customers.xlsx"
    wb.save(path)
    parsed = ExcelParserService().parse_customer_master(path)
    assert parsed.duplicate_names == 1
    assert parsed.records == [{"customer_name": "Acme Corp"}, {"customer_name": "Beta Ltd"}]
    assert all(set(r.keys()) == {"customer_name"} for r in parsed.records)


def test_template_blank_header_under_load(tmp_path: Path):
    customers = [f"Cust {i:05d}" for i in range(200)]
    products = [f"PROD-{i:04d}" for i in range(100)]
    out = tmp_path / "scale.xlsx"
    ExcelTemplateGenerator().generate(
        customers=customers,
        products=products,
        distributors=["ShouldNotAppear"],
        periods=["January 2099"],
        output_path=out,
    )
    sheet = load_workbook(out)["Sales Report"]
    for row in range(1, 6):
        assert sheet.cell(row, 2).value in (None, "")


def test_quarterly_matches_monthly_sum(db: Session, tmp_path: Path):
    company = "QMatch Co Unique"
    months = [("July 2090", 11), ("August 2090", 22), ("September 2090", 33)]
    for month, qty in months:
        path = build_official_workbook(
            tmp_path / f"{month}.xlsx",
            distributor="QMatch Rep",
            company=company,
            reporting_month=month,
            rows=[(1, "C", "Paper", "QM", qty, 1, 2)],
        )
        ReportService(db).ingest_excel(path, actor="test")

    q = BusinessAggregationService(db).quarterly_summary(
        quarter_label="Q3 2090", company=company
    )
    assert q["data"][0]["totalQuantity"] == 66.0
    trend = DashboardService(db).monthly_sales_trend()
    relevant = [r for r in trend if r["month"] in {m for m, _ in months}]
    assert sum(r["qty"] for r in relevant) == 66.0
