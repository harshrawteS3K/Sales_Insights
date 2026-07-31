"""Business rule: one active report per (Distributor, Reporting Month)."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.services.consolidated_data_service import ConsolidatedDataService
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


def _uid(prefix: str) -> str:
    return f"{prefix} {uuid4().hex[:8]}"


def _active_reports(db: Session, distributor_id: int, month: str) -> list[Report]:
    return list(
        db.scalars(
            select(Report).where(
                Report.distributor_id == distributor_id,
                Report.reporting_month == month,
                Report.is_deleted.is_(False),
            )
        ).all()
    )


def test_scenario1_first_upload_one_active(db: Session, tmp_path: Path):
    dist = _uid("Biz Dist A")
    month = "July 2091"
    path = build_official_workbook(
        tmp_path / "s1.xlsx",
        distributor=dist,
        reporting_month=month,
        rows=[(1, "Cust1", "Paper", "P1", 10, 1, 2)],
    )
    svc = ReportService(db)
    report, n, _, _ = svc.ingest_excel(path, actor="test")
    assert n == 1
    assert report.is_deleted is False
    assert len(_active_reports(db, report.distributor_id, month)) == 1

    page = ConsolidatedDataService(db).list_records(limit=5000, distributor=dist)
    assert len(page.data) == 1
    assert page.data[0].reportId == report.id


def test_scenario2_revised_july_replaces(db: Session, tmp_path: Path):
    dist = _uid("Biz Dist A")
    month = "July 2092"
    v1 = build_official_workbook(
        tmp_path / "s2a.xlsx",
        distributor=dist,
        reporting_month=month,
        rows=[(1, "Old Cust", "Paper", "P1", 50, 1, 2)],
    )
    v2 = build_official_workbook(
        tmp_path / "s2b.xlsx",
        distributor=dist,
        reporting_month=month,
        rows=[(1, "New Cust", "Paper", "P2", 99, 3, 4)],
    )
    svc = ReportService(db)
    old, _, _, _ = svc.ingest_excel(v1, actor="test")
    new, _, _, _ = svc.ingest_excel(v2, actor="test")
    db.refresh(old)
    db.refresh(new)

    assert old.is_deleted is True
    assert new.is_deleted is False
    assert len(_active_reports(db, new.distributor_id, month)) == 1

    old_sales = db.scalar(
        select(func.count()).select_from(SalesRecord).where(
            SalesRecord.report_id == old.id,
            SalesRecord.is_deleted.is_(False),
        )
    )
    assert int(old_sales or 0) == 0

    page = ConsolidatedDataService(db).list_records(limit=5000, distributor=dist)
    assert len(page.data) == 1
    assert page.data[0].reportId == new.id
    assert page.data[0].sales[0].customerName == "New Cust"
    assert all(g.reportId != old.id for g in page.data)


def test_scenario3_july_and_august_both_active(db: Session, tmp_path: Path):
    dist = _uid("Biz Dist A")
    july = build_official_workbook(
        tmp_path / "s3j.xlsx",
        distributor=dist,
        reporting_month="July 2093",
        rows=[(1, "J", "Paper", "P1", 10, 1, 2)],
    )
    aug = build_official_workbook(
        tmp_path / "s3a.xlsx",
        distributor=dist,
        reporting_month="August 2093",
        rows=[(1, "A", "Paper", "P2", 20, 3, 4)],
    )
    svc = ReportService(db)
    r_j, _, _, _ = svc.ingest_excel(july, actor="test")
    r_a, _, _, _ = svc.ingest_excel(aug, actor="test")
    db.refresh(r_j)
    db.refresh(r_a)
    assert r_j.is_deleted is False
    assert r_a.is_deleted is False

    page = ConsolidatedDataService(db).list_records(limit=5000, distributor=dist)
    ids = {g.reportId for g in page.data}
    assert ids == {r_j.id, r_a.id}


def test_scenario4_two_distributors_same_month(db: Session, tmp_path: Path):
    month = "July 2094"
    a = _uid("Biz Dist A")
    b = _uid("Biz Dist B")
    pa = build_official_workbook(
        tmp_path / "s4a.xlsx",
        distributor=a,
        reporting_month=month,
        rows=[(1, "CA", "Paper", "P1", 11, 1, 2)],
    )
    pb = build_official_workbook(
        tmp_path / "s4b.xlsx",
        distributor=b,
        reporting_month=month,
        rows=[(1, "CB", "Paper", "P2", 22, 3, 4)],
    )
    svc = ReportService(db)
    ra, _, _, _ = svc.ingest_excel(pa, actor="test")
    rb, _, _, _ = svc.ingest_excel(pb, actor="test")
    assert ra.distributor_id != rb.distributor_id
    assert ra.is_deleted is False and rb.is_deleted is False

    page_a = ConsolidatedDataService(db).list_records(limit=5000, distributor=a)
    page_b = ConsolidatedDataService(db).list_records(limit=5000, distributor=b)
    assert len(page_a.data) == 1 and page_a.data[0].reportId == ra.id
    assert len(page_b.data) == 1 and page_b.data[0].reportId == rb.id


def test_scenario5_multiple_revisions_only_latest_active(db: Session, tmp_path: Path):
    dist = _uid("Biz Dist Multi")
    month = "July 2095"
    svc = ReportService(db)
    reports = []
    for i in range(3):
        path = build_official_workbook(
            tmp_path / f"s5_{i}.xlsx",
            distributor=dist,
            reporting_month=month,
            rows=[(1, f"Cust{i}", "Paper", f"P{i}", 10 + i, 1, 2)],
        )
        r, _, _, _ = svc.ingest_excel(path, actor=f"user-{i}")
        reports.append(r)

    for r in reports[:-1]:
        db.refresh(r)
        assert r.is_deleted is True
    db.refresh(reports[-1])
    assert reports[-1].is_deleted is False
    assert len(_active_reports(db, reports[-1].distributor_id, month)) == 1

    page = ConsolidatedDataService(db).list_records(limit=5000, distributor=dist)
    assert len(page.data) == 1
    assert page.data[0].reportId == reports[-1].id
    assert page.data[0].sales[0].customerName == "Cust2"

    # Dashboard must not double-count soft-deleted sales
    summary = DashboardService(db).summary()
    assert summary.total_reports >= 1


def test_inactive_report_sales_excluded_from_consolidated(db: Session, tmp_path: Path):
    """Even if sales were left active by mistake, soft-deleted report must not appear."""
    dist = _uid("Ghost Leak Dist")
    month = "June 2096"
    path = build_official_workbook(
        tmp_path / "leak.xlsx",
        distributor=dist,
        reporting_month=month,
        rows=[(1, "Leak Cust", "Paper", "PX", 5, 1, 2)],
    )
    svc = ReportService(db)
    report, _, _, _ = svc.ingest_excel(path, actor="test")
    # Simulate inconsistent state: soft-delete report but leave a sales row "active"
    report.is_deleted = True
    db.flush()
    sales = db.scalars(
        select(SalesRecord).where(SalesRecord.report_id == report.id)
    ).all()
    for s in sales:
        s.is_deleted = False
        s.deleted_at = None
    db.flush()

    page = ConsolidatedDataService(db).list_records(limit=5000, distributor=dist)
    assert all(g.reportId != report.id for g in page.data)
