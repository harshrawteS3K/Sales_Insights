"""Prompt 2 — Quarterly-only application migration regression."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.audit_trail import AuditTrail
from app.models.report import Report
from app.schemas.sales_record import (
    ConsolidatedFilterOptions,
    DeleteReportPreview,
    DeleteReportRequest,
    ReportSalesGroup,
)
from app.services.consolidated_data_service import ConsolidatedDataService
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService
from app.utils.period_calendar import parse_quarter_label
from app.utils.reporting_month import normalize_reporting_month
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


def _uid(prefix: str) -> str:
    return f"{prefix} {uuid4().hex[:8]}"


def test_delete_request_prefers_reporting_quarter():
    req = DeleteReportRequest(
        distributor="Acme",
        reportingQuarter="Q2 2026",
        reportingMonth="July 2099",
    )
    assert req.resolved_month() == "Q2 2026"
    assert req.reportingQuarter == "Q2 2026"
    assert req.reportingMonth == "Q2 2026"


def test_delete_preview_syncs_quarter_alias():
    preview = DeleteReportPreview(
        distributor="Acme",
        reportingMonth="Q1 2026",
        rowCount=3,
    )
    assert preview.reportingQuarter == "Q1 2026"
    assert preview.reportingMonth == "Q1 2026"


def test_report_sales_group_exposes_reporting_quarter():
    group = ReportSalesGroup(
        reportId=1,
        distributor="Acme",
        reportingMonth="Q3 2026",
        recordCount=0,
        sales=[],
    )
    assert group.reportingQuarter == "Q3 2026"
    assert group.reportingMonth == "Q3 2026"


def test_filter_options_expose_reporting_quarters():
    opts = ConsolidatedFilterOptions(
        reportingMonths=["Q1 2026", "Q2 2026"],
    )
    assert opts.reportingQuarters == ["Q1 2026", "Q2 2026"]


def test_period_spec_includes_quarter_label():
    spec = parse_quarter_label("Q2 2026")
    assert spec is not None
    assert "Q2 2026" in spec.month_list


def test_quarterly_duplicate_detection(db: Session, tmp_path: Path):
    dist = _uid("QOnly Dist")
    quarter = "Q2 2095"
    path1 = build_official_workbook(
        tmp_path / "q1.xlsx",
        distributor=dist,
        reporting_month=quarter,
        rows=[(1, "Cust A", "Seg", "P1", 10)],
    )
    path2 = build_official_workbook(
        tmp_path / "q2.xlsx",
        distributor=dist,
        reporting_month=quarter,
        rows=[(1, "Cust B", "Seg", "P1", 20)],
    )

    svc = ReportService(db)
    first, _, _, _ = svc.ingest_excel(path1, actor="tester")
    second, _, _, _ = svc.ingest_excel(path2, actor="tester")

    assert first.reporting_month == normalize_reporting_month(quarter)
    assert second.reporting_month == normalize_reporting_month(quarter)

    db.refresh(first)
    db.refresh(second)
    assert first.is_deleted is True
    assert second.is_deleted is False

    active = list(
        db.scalars(
            select(Report).where(
                Report.reporting_month == quarter,
                Report.is_deleted.is_(False),
            )
        )
    )
    # Only the latest revision for this distributor+quarter remains active
    active_for_dist = [r for r in active if r.id in {first.id, second.id}]
    assert len(active_for_dist) == 1
    assert active_for_dist[0].id == second.id

    page = ConsolidatedDataService(db).list_records(limit=5000, distributor=dist)
    assert len(page.data) == 1
    assert page.data[0].reportId == second.id
    assert page.data[0].reportingQuarter == quarter


def test_trend_includes_quarter_key(db: Session, tmp_path: Path):
    dist = _uid("Trend Dist")
    quarter = "Q1 2096"
    path = build_official_workbook(
        tmp_path / "trend.xlsx",
        distributor=dist,
        reporting_month=quarter,
        rows=[(1, "Cust", "Seg", "P1", 5)],
    )
    ReportService(db).ingest_excel(path, actor="tester")
    rows = DashboardService(db).monthly_sales_trend(distributor=dist)
    match = [r for r in rows if r.get("month") == quarter or r.get("quarter") == quarter]
    assert match, f"expected quarter in trend: {rows}"
    assert match[0].get("quarter") == quarter


def test_export_audit_uses_quarterly_terminology(db: Session):
    ConsolidatedDataService(db).log_export(actor="q-only-tester", total=12, filters_summary="")
    entry = db.scalars(
        select(AuditTrail)
        .where(AuditTrail.user_name == "q-only-tester")
        .order_by(AuditTrail.id.desc())
    ).first()
    assert entry is not None
    assert "Exported Quarterly Report" in (entry.details or "")
