"""Regression tests for data quality summary, viz Top-N, and ACTIVE-only filters."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService
from app.utils.validation_summary import build_validation_summary, validation_user_message
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


def test_validation_summary_includes_confidence():
    summary = build_validation_summary(
        expected_rows=10,
        imported_rows=7,
        incomplete_rows=3,
        row_errors=["Row 2: Missing Customer", "Row 3: Blank row"],
        confidence_score=73,
    )
    assert summary["confidence_score"] == 73
    assert summary["skipped_rows"] == 3
    msg = validation_user_message(summary)
    assert msg and "skipped" in msg.lower()


def test_validation_message_when_confidence_low_no_skips():
    summary = {
        "total_rows": 5,
        "imported_rows": 5,
        "skipped_rows": 0,
        "warning_count": 0,
        "warnings": [],
        "confidence_score": 90,
    }
    assert validation_user_message(summary) is None


def test_frontend_report_exposes_confidence_and_dq(db: Session, tmp_path: Path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Name of Distributor"
    ws["B1"] = "DQ Dist Viz"
    ws["A2"] = "Company Name"
    ws["B2"] = "Co"
    ws["A3"] = "Address"
    ws["B3"] = "Addr"
    ws["A4"] = "Phone No"
    ws["B4"] = "1"
    ws["A5"] = "Reporting Month"
    ws["B5"] = "May 2099"
    headers = [
        "Sr. No.",
        "Name of Customer",
        "Segment",
        "Product",
        "Opening Stock",
        "Closing Stock",
        "Quantity",
    ]
    for i, h in enumerate(headers, 1):
        ws.cell(9, i, h)
    for c, v in enumerate([1, "Cust A", "Paper", "P1", 1, 2, 10], 1):
        ws.cell(10, c, v)
    for c, v in enumerate([2, "", "Paper", "", 1, 2, 5], 1):
        ws.cell(11, c, v)
    path = tmp_path / "dq.xlsx"
    wb.save(path)

    report, inserted, _, _ = ReportService(db).ingest_excel(path, actor="test")
    assert inserted == 1
    fe = ReportService(db).to_frontend_reports([report])[0]
    assert fe.confidenceScore is not None
    assert fe.confidenceScore < 100
    assert fe.incompleteRows == 1
    assert fe.validationSummary
    assert fe.validationSummary.get("confidence_score") == fe.confidenceScore
    assert fe.validationMessage


def test_product_bar_top_n_others(db: Session, tmp_path: Path):
    # Build workbook with many products
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Name of Distributor"
    ws["B1"] = "TopN Dist"
    ws["A2"] = "Company Name"
    ws["B2"] = "Co"
    ws["A3"] = "Address"
    ws["B3"] = "Addr"
    ws["A4"] = "Phone No"
    ws["B4"] = "1"
    ws["A5"] = "Reporting Month"
    ws["B5"] = "June 2099"
    headers = [
        "Sr. No.",
        "Name of Customer",
        "Segment",
        "Product",
        "Opening Stock",
        "Closing Stock",
        "Quantity",
    ]
    for i, h in enumerate(headers, 1):
        ws.cell(9, i, h)
    for i in range(15):
        row = 10 + i
        for c, v in enumerate(
            [i + 1, f"Cust {i}", "Paper", f"Prod{i:02d}", 1, 2, 100 - i], 1
        ):
            ws.cell(row, c, v)
    path = tmp_path / "topn.xlsx"
    wb.save(path)
    ReportService(db).ingest_excel(path, actor="test")

    bar = DashboardService(db).product_bar(period="June 2099", top_n=10)
    assert len(bar) == 11  # 10 + Others
    assert bar[-1]["product"] == "Others"
    assert bar[-1]["qty"] > 0


def test_monthly_trend_and_heatmap_active_only(db: Session, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "trend.xlsx",
        distributor="Trend Dist",
        reporting_month="July 2099",
        rows=[(1, "C1", "Paper", "TP1", 50, 1, 2)],
    )
    ReportService(db).ingest_excel(path, actor="test")
    svc = DashboardService(db)
    trend = svc.monthly_sales_trend()
    assert any(r["month"] == "July 2099" for r in trend)
    heat = svc.distributor_month_heatmap()
    assert "July 2099" in heat["months"] or any(
        c["month"] == "July 2099" for c in heat["cells"]
    )
    contrib = svc.distributor_contribution(period="July 2099")
    assert contrib
    total_pct = sum(float(c["value"]) for c in contrib)
    assert 99 <= total_pct <= 101


def test_dashboard_analytics_filter_uses_company(db: Session, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "filt.xlsx",
        distributor="Filter Match Dist",
        company="Filter Match Company Unique",
        reporting_month="August 2099",
        rows=[(1, "C1", "Paper", "FP1", 20, 1, 2)],
    )
    ReportService(db).ingest_excel(path, actor="test")
    opts = DashboardService(db).distributor_filter_options()
    assert "Filter Match Company Unique" in (opts.distributor or [])
    sales_names = {r.name for r in DashboardService(db).distributor_totals()}
    for name in opts.distributor or []:
        if name == "All":
            continue
        assert name in sales_names
