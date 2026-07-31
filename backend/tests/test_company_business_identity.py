"""Business identity: one ACTIVE report per Distributor Company + Reporting Month."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.distributor import Distributor
from app.models.report import Report
from app.services.business_aggregation_service import BusinessAggregationService
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


def test_different_reps_same_company_same_month_replace(db: Session, tmp_path: Path):
    """Representative change must REPLACE — never create a second ACTIVE report."""
    company = _uid("Pune Dyes & Chemical Co.")
    month = "August 2095"

    v1 = build_official_workbook(
        tmp_path / "rep1.xlsx",
        distributor="Anshul Deshmukh",
        company=company,
        reporting_month=month,
        rows=[(1, "Cust", "Paper", "P1", 100, 1, 2)],
    )
    r1, n1, _, _ = ReportService(db).ingest_excel(v1, actor="test")
    assert n1 == 1
    assert r1.is_deleted is False

    v2 = build_official_workbook(
        tmp_path / "rep2.xlsx",
        distributor="Another Employee",
        company=company,
        reporting_month=month,
        rows=[(1, "Cust", "Paper", "P1", 55, 1, 2)],
    )
    r2, n2, _, _ = ReportService(db).ingest_excel(v2, actor="test")
    assert n2 == 1
    assert r2.is_deleted is False

    db.refresh(r1)
    assert r1.is_deleted is True

    # Exactly one ACTIVE report for this company + month
    active = list(
        db.scalars(
            select(Report)
            .join(Distributor, Distributor.id == Report.distributor_id)
            .where(
                Report.is_deleted.is_(False),
                Report.reporting_month == month,
                Distributor.company == company,
            )
        ).all()
    )
    assert len(active) == 1
    assert active[0].id == r2.id

    # Same company master row; representative updated to latest
    dist = db.get(Distributor, r2.distributor_id)
    assert dist is not None
    assert dist.company == company
    assert dist.name == "Another Employee"

    # Only one distributor row for this company
    company_rows = list(
        db.scalars(
            select(Distributor).where(
                Distributor.is_deleted.is_(False),
                Distributor.company == company,
            )
        ).all()
    )
    assert len(company_rows) == 1


def test_quarterly_reflects_company_replacement(db: Session, tmp_path: Path):
    company = _uid("Q Company Identity")
    for month, qty, rep in [
        ("January 2094", 10, "Rep One"),
        ("February 2094", 20, "Rep One"),
        ("March 2094", 30, "Rep One"),
    ]:
        path = build_official_workbook(
            tmp_path / f"{month}.xlsx",
            distributor=rep,
            company=company,
            reporting_month=month,
            rows=[(1, "C", "Paper", "P", qty, 1, 2)],
        )
        ReportService(db).ingest_excel(path, actor="test")

    # Replace January with different representative
    path2 = build_official_workbook(
        tmp_path / "jan2.xlsx",
        distributor="Rep Two",
        company=company,
        reporting_month="January 2094",
        rows=[(1, "C", "Paper", "P", 7, 1, 2)],
    )
    ReportService(db).ingest_excel(path2, actor="test")

    summary = BusinessAggregationService(db).quarterly_summary(
        quarter_label="Q1 2094", company=company
    )
    assert summary["totalCompanies"] == 1
    assert summary["data"][0]["totalQuantity"] == 57.0  # 7+20+30
    assert "salesValue" not in summary["data"][0]
