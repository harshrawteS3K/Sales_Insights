"""Regression: quarterly aggregation, company entity, period calendar."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.services.business_aggregation_service import BusinessAggregationService
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService
from app.utils.period_calendar import (
    available_quarter_labels,
    months_for_quarter,
    parse_quarter_label,
    period_spec_for_quarter,
)
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


def test_period_calendar_q1_months():
    months = months_for_quarter(1, 2026)
    assert months == ("January 2026", "February 2026", "March 2026")
    spec = parse_quarter_label("Q1 2026")
    assert spec is not None
    assert spec.month_list == list(months)


def test_available_quarters_from_months():
    labels = available_quarter_labels(
        ["January 2026", "March 2026", "April 2026", "July 2025"]
    )
    assert "Q1 2026" in labels
    assert "Q2 2026" in labels
    assert "Q3 2025" in labels


def test_quarterly_totals_equal_sum_of_months(db: Session, tmp_path: Path):
    company = "Puneet Dyes & Chemicals QTest"
    rep = "Navneet Goel QTest Unique"
    for month, qty in [
        ("January 2098", 10),
        ("February 2098", 20),
        ("March 2098", 30),
    ]:
        path = build_official_workbook(
            tmp_path / f"{month.replace(' ', '_')}.xlsx",
            distributor=rep,
            company=company,
            reporting_month=month,
            rows=[(1, "Cust", "Paper", "ProdA", qty, 1, 2)],
        )
        ReportService(db).ingest_excel(path, actor="test")

    engine = BusinessAggregationService(db)
    summary = engine.quarterly_summary(quarter_label="Q1 2098", company=company)
    assert summary["totalCompanies"] == 1
    row = summary["data"][0]
    assert row["company"] == company
    assert row["totalQuantity"] == 60.0
    assert set(row["monthsSubmitted"]) == {
        "January 2098",
        "February 2098",
        "March 2098",
    }
    assert row["reportsIncluded"] == 3

    report = engine.quarterly_report(company=company, quarter_label="Q1 2098")
    assert report["totalQuantity"] == 60.0
    assert report["products"][0]["product"] == "ProdA"
    assert report["products"][0]["quantity"] == 60.0
    assert report["unit"] == "MT"


def test_replaced_month_excluded_from_quarter(db: Session, tmp_path: Path):
    company = "Replace Co Q Unique"
    rep = "Rep Replace Unique"
    for month, qty in [("January 2097", 100), ("February 2097", 50)]:
        path = build_official_workbook(
            tmp_path / f"base_{month}.xlsx",
            distributor=rep,
            company=company,
            reporting_month=month,
            rows=[(1, "C", "Paper", "P", qty, 1, 2)],
        )
        ReportService(db).ingest_excel(path, actor="test")

    # Replace January with new ACTIVE report (qty 5)
    path2 = build_official_workbook(
        tmp_path / "jan_replaced.xlsx",
        distributor=rep,
        company=company,
        reporting_month="January 2097",
        rows=[(1, "C", "Paper", "P", 5, 1, 2)],
    )
    ReportService(db).ingest_excel(path2, actor="test")

    summary = BusinessAggregationService(db).quarterly_summary(
        quarter_label="Q1 2097", company=company
    )
    assert summary["data"][0]["totalQuantity"] == 55.0  # 5 + 50, not 100+50
    assert summary["data"][0]["reportsIncluded"] == 2


def test_aggregator_uses_company_not_representative(db: Session, tmp_path: Path):
    """Two reps under same company should roll into one company row."""
    company = "Shared Company LLC"
    for rep, month, qty in [
        ("Rep A", "April 2096", 10),
        ("Rep B", "May 2096", 15),
    ]:
        # Same company, different representative names → get_or_create_by_name
        # creates separate distributor rows; company field still Shared Company LLC
        path = build_official_workbook(
            tmp_path / f"{rep}.xlsx",
            distributor=rep,
            company=company,
            reporting_month=month,
            rows=[(1, "C", "Paper", "P", qty, 1, 2)],
        )
        ReportService(db).ingest_excel(path, actor="test")

    totals = DashboardService(db).distributor_totals(period=None)
    companies = [t.name for t in totals]
    # Aggregation key is company
    assert company in companies
    # Should not chart by representative as primary key when company present
    row = next(t for t in totals if t.name == company)
    # Q2 months April+May → may appear in different periods; without period filter sum both
    assert row.qty >= 25.0


def test_dashboard_kpi_unit_label_mt(db: Session):
    summary = DashboardService(db).summary()
    labels = [k.label for k in summary.kpis]
    assert any("MT" in lab for lab in labels)
    assert not any("KG" in lab for lab in labels)
