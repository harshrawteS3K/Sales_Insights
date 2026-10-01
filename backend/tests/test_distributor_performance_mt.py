"""Distributor Performance MT must equal Consolidated Data MT for the same filters."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.enums import ReportStatus
from app.models.distributor import Distributor
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.services.consolidated_data_service import ConsolidatedDataService
from app.services.distributor_performance_service import DistributorPerformanceService


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


def _seed(
    db: Session,
    company: str,
    rows: list[tuple[str, float, str, str]],
    *,
    report_deleted: bool = False,
    row_deleted: bool = False,
    month: str = "April 2026",
) -> Distributor:
    dist = db.query(Distributor).filter(Distributor.company == company).one_or_none()
    if dist is None:
        dist = Distributor(name=company, company=company, is_active=True)
        db.add(dist)
        db.flush()
    report = Report(
        name=f"{company}-{uuid.uuid4().hex[:6]}",
        distributor_id=dist.id,
        reporting_month=month,
        status=ReportStatus.PROCESSED.value,
        is_deleted=report_deleted,
    )
    db.add(report)
    db.flush()
    for customer, qty, unit, original_unit in rows:
        db.add(
            SalesRecord(
                report_id=report.id,
                distributor_id=dist.id,
                customer_name=customer,
                segment="Paper",
                product="APCOFLEX N745",
                quantity=Decimal(str(qty)),
                unit=unit,
                original_unit=original_unit,
                period=month,
                row_hash=uuid.uuid4().hex,
                is_deleted=row_deleted,
            )
        )
    db.flush()
    return dist


def _consolidated_mt(db: Session, company: str) -> float:
    page = ConsolidatedDataService(db).list_records(
        company=company, skip=0, limit=500, page_by="reports"
    )
    return round(
        sum(float(line.quantity.replace(",", "")) for group in page.data for line in group.sales),
        3,
    )


def test_distributor_performance_matches_consolidated_mt(db: Session):
    tag = uuid.uuid4().hex[:6]
    kg_co = f"DP KG Co {tag}"
    mt_co = f"DP MT Co {tag}"

    _seed(db, kg_co, [("Cust A", 3000, "KG", "KG"), ("Cust B", 5500, "KG", "KG")])
    _seed(db, mt_co, [("Cust C", 65, "MT", "MT"), ("Cust D", 33.44, "MT", "KG")])
    # Deleted / replaced data must not be counted.
    _seed(db, kg_co, [("Cust A", 99999, "MT", "MT")], report_deleted=True)
    _seed(db, mt_co, [("Cust C", 77777, "MT", "MT")], row_deleted=True, month="May 2026")

    result = DistributorPerformanceService(db).performance(
        allowed_companies=[kg_co, mt_co],
    )
    by_name = {r["distributor"]: r for r in result["ranking"]}

    assert by_name[kg_co]["sales_mt"] == pytest.approx(8.5, abs=1e-9)
    assert by_name[kg_co]["sales_mt_display"] == "8.500"
    assert by_name[mt_co]["sales_mt"] == pytest.approx(98.44, abs=1e-9)
    assert by_name[mt_co]["sales_mt_display"] == "98.440"

    kg_customers = {c["customer"]: c["sales_mt_display"] for c in by_name[kg_co]["customer_contribution"]}
    assert kg_customers == {"Cust A": "3.000", "Cust B": "5.500"}
    mt_customers = {c["customer"]: c["sales_mt_display"] for c in by_name[mt_co]["customer_contribution"]}
    assert mt_customers == {"Cust C": "65.000", "Cust D": "33.440"}

    dp_total = round(sum(r["sales_mt"] for r in result["ranking"]), 3)
    consolidated_total = round(_consolidated_mt(db, kg_co) + _consolidated_mt(db, mt_co), 3)
    print(f"\nDistributor Performance MT={dp_total:.3f} Consolidated MT={consolidated_total:.3f}")
    assert dp_total == pytest.approx(106.94, abs=1e-9)
    assert dp_total == consolidated_total
