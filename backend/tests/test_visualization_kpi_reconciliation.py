"""Visualization KPIs and quarterly totals come from the same consolidated rows."""

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
from app.services.sales_insights_service import SalesInsightsService
from app.utils.period_calendar import fy_quarter_label


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


def _add_report(db: Session, dist: Distributor, period: str) -> Report:
    report = Report(
        name=f"{dist.company}-{period}-{uuid.uuid4().hex[:6]}",
        distributor_id=dist.id,
        reporting_month=period,
        status=ReportStatus.PROCESSED.value,
        is_deleted=False,
    )
    db.add(report)
    db.flush()
    return report


def _add_sale(
    db: Session,
    report: Report,
    dist: Distributor,
    *,
    customer: str,
    product: str,
    quantity: str,
    unit: str,
    original_unit: str,
) -> None:
    db.add(
        SalesRecord(
            report_id=report.id,
            distributor_id=dist.id,
            customer_name=customer,
            segment="Rubber",
            product=product,
            quantity=Decimal(quantity),
            unit=unit,
            original_unit=original_unit,
            period=report.reporting_month,
            location="West",
            row_hash=uuid.uuid4().hex,
            is_deleted=False,
        )
    )


def test_kpis_reconcile_with_quarters_and_count_each_row_once(db: Session):
    company = f"KPI Recon {uuid.uuid4().hex[:8]}"
    dist = Distributor(name=f"{company} Rep", company=company, is_active=True, is_deleted=False)
    db.add(dist)
    db.flush()

    q1 = fy_quarter_label(2026, 1)
    q2 = fy_quarter_label(2026, 2)
    q1_report = _add_report(db, dist, q1)
    q2_report = _add_report(db, dist, q2)
    _add_sale(
        db, q1_report, dist,
        customer="Royal Composites Pvt. Ltd.",
        product="APCOFLEX N385",
        quantity="10.500",
        unit="MT",
        original_unit="MT",
    )
    _add_sale(
        db, q1_report, dist,
        customer="ROYAL COMPOSITES PVT. LTD.",
        product="Apcoflex N-385",
        quantity="5.000",
        unit="MT",
        original_unit="KG",
    )
    _add_sale(
        db, q1_report, dist,
        customer="Other Customer",
        product="APCOFLEX N745",
        quantity="20.000",
        unit="MT",
        original_unit="MT",
    )
    _add_sale(
        db, q1_report, dist,
        customer="Third Customer",
        product="APCOFLEX N745 NBR",
        quantity="1.250",
        unit="MT",
        original_unit="MT",
    )
    _add_sale(
        db, q2_report, dist,
        customer="Fourth Customer",
        product="APCOFLEX N745",
        quantity="50.600",
        unit="MT",
        original_unit="MT",
    )
    _add_sale(
        db, q2_report, dist,
        customer="Fifth Customer",
        product="APCOFLEX N385",
        quantity="7000",
        unit="KG",
        original_unit="KG",
    )
    db.flush()

    payload = SalesInsightsService(db).sales_insights(
        distributor=company,
        fiscal_year_start=2026,
        period="full_year",
    )
    kpis = payload["kpis"]
    by_q = {row["quarter"]: row for row in payload["quarterly_totals"]}

    assert payload["record_count"] == 6
    assert by_q[1]["record_count"] == 4
    assert by_q[2]["record_count"] == 2
    assert by_q[3]["record_count"] == 0
    assert by_q[4]["record_count"] == 0
    assert by_q[1]["sales_mt"] == pytest.approx(36.750, abs=0.001)
    # 50.600 MT + 7000 KG once → 57.600, never 7050.600 and never 0.058
    assert by_q[2]["sales_mt"] == pytest.approx(57.600, abs=0.001)
    assert by_q[3]["sales_mt"] == pytest.approx(0.0, abs=0.001)
    assert by_q[4]["sales_mt"] == pytest.approx(0.0, abs=0.001)
    quarter_sum = sum(row["sales_mt"] for row in payload["quarterly_totals"])
    assert quarter_sum == pytest.approx(kpis["total_sales_mt"], abs=0.001)
    assert kpis["total_sales_mt"] == pytest.approx(94.350, abs=0.001)
    assert kpis["total_sales_mt"] != pytest.approx(7086.750, abs=1)
    # Q3 and Q4 have no records, so the average uses Q1 and Q2 only.
    assert kpis["average_quarterly_sales_mt"] == pytest.approx(94.350 / 2, abs=0.001)
    assert kpis["total_customers"] == 5
    assert kpis["total_products"] == 3

    q2_only = SalesInsightsService(db).sales_insights(
        distributor=company,
        fiscal_year_start=2026,
        period="q2",
    )
    assert q2_only["kpis"]["total_sales_mt"] == pytest.approx(57.600, abs=0.001)
    q2_sum = sum(row["sales_mt"] for row in q2_only["quarterly_totals"])
    assert q2_sum == pytest.approx(q2_only["kpis"]["total_sales_mt"], abs=0.001)
    assert q2_only["kpis"]["average_quarterly_sales_mt"] == pytest.approx(57.600, abs=0.001)

    n385 = SalesInsightsService(db).sales_insights(
        distributor=company,
        fiscal_year_start=2026,
        period="full_year",
        product="APCOFLEX N385",
    )
    assert n385["kpis"]["total_products"] == 1
    assert n385["kpis"]["total_sales_mt"] == pytest.approx(22.500, abs=0.001)
    assert sum(row["sales_mt"] for row in n385["quarterly_totals"]) == pytest.approx(22.500, abs=0.001)
