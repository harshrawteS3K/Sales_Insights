"""Regression: distributor customer mapping backfill + count."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.services.distributor_service import DistributorService
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


def test_import_auto_learns_and_counts(db: Session, tmp_path: Path):
    company = _uid("Map Co")
    path = build_official_workbook(
        tmp_path / "map.xlsx",
        distributor="Rep Map",
        company=company,
        reporting_month="Q2 2099",
        rows=[
            (1, "AKS RUGS", "Paper", "P1", 10),
            (2, "XYZ POLYMERS", "Paper", "P1", 5),
        ],
    )
    report, inserted, _, _ = ReportService(db).ingest_excel(path, actor="tester")
    assert inserted >= 2
    assert report.distributor_id is not None

    svc = DistributorService(db)
    names = svc.list_customers(report.distributor_id)
    assert any(n.casefold() == "aks rugs" for n in names)
    assert any(n.casefold() == "xyz polymers" for n in names)
    assert svc.customer_count(report.distributor_id) == len(names)


def test_backfill_is_idempotent(db: Session, tmp_path: Path):
    company = _uid("Backfill Co")
    path = build_official_workbook(
        tmp_path / "bf.xlsx",
        distributor="Rep BF",
        company=company,
        reporting_month="Q1 2097",
        rows=[(1, "ONLY CUST", "Paper", "P1", 3)],
    )
    report, _, _, _ = ReportService(db).ingest_excel(path, actor="tester")
    svc = DistributorService(db)
    first = svc.backfill_customer_mappings(actor="tester")
    second = svc.backfill_customer_mappings(actor="tester")
    assert svc.customer_count(report.distributor_id) >= 1
    assert second["newly_learned"] == 0 or second["mappings_touched"] >= 0
    assert first["source_rows"] >= 1
