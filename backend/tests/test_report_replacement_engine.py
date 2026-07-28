"""Regression tests for business-aware report replacement (Distributor + Reporting Month)."""

from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.database.session import SessionLocal
from app.exceptions import ConflictError, ExcelProcessingError, ValidationAppError
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.services.report_service import ReportService
from tests.workbook_helpers import build_official_workbook


def _wb(
    path: Path,
    *,
    distributor: str,
    month: str,
    customers: list[tuple],
) -> Path:
    rows = []
    for i, (customer, segment, product, qty) in enumerate(customers, 1):
        rows.append((i, customer, segment, product, qty, 100, 10))
    return build_official_workbook(
        path,
        distributor=distributor,
        reporting_month=month,
        rows=rows,
        include_stock=True,
    )


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


@pytest.fixture
def service(db) -> ReportService:
    return ReportService(db)


def test_scenario1_new_distributor_inserts(service: ReportService, tmp_path: Path, db):
    dist = f"Dist New {uuid4().hex[:8]}"
    path = _wb(
        tmp_path / "new.xlsx",
        distributor=dist,
        month="January 2099",
        customers=[("Cust A", "Carpet", "APCOTEX CB 4600", 100)],
    )
    report, inserted, dup, score = service.ingest_excel(path, actor="test")
    assert dup is False
    assert inserted == 1
    assert report.distributor_id is not None
    assert report.reporting_month == "January 2099"
    assert report.confidence_score == score
    assert report.is_deleted is False


def test_scenario2_same_distributor_different_month(service: ReportService, tmp_path: Path, db):
    dist = f"Dist Months {uuid4().hex[:8]}"
    p1 = _wb(
        tmp_path / "p1.xlsx",
        distributor=dist,
        month="February 2099",
        customers=[("Cust A", "Carpet", "APCOTEX CB 4600", 10)],
    )
    p2 = _wb(
        tmp_path / "p2.xlsx",
        distributor=dist,
        month="March 2099",
        customers=[("Cust B", "Carpet", "APCOTEX CB 300", 20)],
    )
    r1, _, _, _ = service.ingest_excel(p1, actor="test")
    r2, _, _, _ = service.ingest_excel(p2, actor="test")
    assert r1.id != r2.id
    assert r1.is_deleted is False
    assert r2.is_deleted is False
    assert r1.reporting_month != r2.reporting_month


def test_scenario3_business_replacement(service: ReportService, tmp_path: Path, db):
    dist = f"Dist Replace {uuid4().hex[:8]}"
    month = "April 2099"
    v1 = _wb(
        tmp_path / "v1.xlsx",
        distributor=dist,
        month=month,
        customers=[
            ("Cust Old", "Carpet", "APCOTEX CB 4600", 50),
            ("Cust Old2", "Carpet", "APCOTEX CB 300", 25),
        ],
    )
    v2 = _wb(
        tmp_path / "v2.xlsx",
        distributor=dist,
        month=month,
        customers=[("Cust New", "Carpet", "APCOTEX CB 4600", 99)],
    )
    old, old_n, _, _ = service.ingest_excel(v1, actor="test")
    assert old_n == 2
    new, new_n, dup, _ = service.ingest_excel(v2, actor="test")
    assert dup is False
    assert new_n == 1
    assert new.id != old.id

    db.refresh(old)
    assert old.is_deleted is True

    active_sales = list(
        db.scalars(
            select(SalesRecord).where(
                SalesRecord.report_id == old.id,
                SalesRecord.is_deleted.is_(False),
            )
        ).all()
    )
    assert active_sales == []

    active = service.reports.get_active_by_business_key(new.distributor_id, month)
    assert active is not None
    assert active.id == new.id


def test_scenario4_exact_file_duplicate_skipped(service: ReportService, tmp_path: Path, db):
    dist = f"Dist FileDup {uuid4().hex[:8]}"
    path = _wb(
        tmp_path / "same.xlsx",
        distributor=dist,
        month="May 2099",
        customers=[("Cust A", "Carpet", "APCOTEX CB 4600", 11)],
    )
    r1, n1, d1, _ = service.ingest_excel(path, actor="test")
    assert n1 == 1 and d1 is False
    with pytest.raises(ConflictError):
        service.ingest_excel(path, actor="test", mark_duplicate_as_error=True)
    r2, n2, d2, _ = service.ingest_excel(path, actor="test", mark_duplicate_as_error=False)
    assert d2 is True
    assert n2 == 0
    assert r2.id == r1.id


def test_scenario5_parse_failure_no_report(service: ReportService, tmp_path: Path, db):
    dist = f"Dist Ghost {uuid4().hex[:8]}"
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Garbage"
    path = tmp_path / "bad.xlsx"
    wb.save(path)
    with pytest.raises((ExcelProcessingError, ValidationAppError)):
        service.ingest_excel(path, actor="test", report_name=f"{dist}-bad")
    found = list(
        db.scalars(
            select(Report).where(
                Report.name == f"{dist}-bad",
                Report.is_deleted.is_(False),
            )
        ).all()
    )
    assert found == []


def test_scenario6_delete_report_soft_deletes_sales(service: ReportService, tmp_path: Path, db):
    dist = f"Dist Delete {uuid4().hex[:8]}"
    path = _wb(
        tmp_path / "del.xlsx",
        distributor=dist,
        month="June 2099",
        customers=[
            ("Cust A", "Carpet", "APCOTEX CB 4600", 5),
            ("Cust B", "Carpet", "APCOTEX CB 300", 7),
        ],
    )
    report, inserted, _, _ = service.ingest_excel(path, actor="test")
    assert inserted == 2
    service.delete_report(report.id, actor="test")
    db.refresh(report)
    assert report.is_deleted is True
    active_sales = list(
        db.scalars(
            select(SalesRecord).where(
                SalesRecord.report_id == report.id,
                SalesRecord.is_deleted.is_(False),
            )
        ).all()
    )
    assert active_sales == []
