"""Quarterly Overview must SUM consolidated MT quantities with no KG→MT conversion."""

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
from app.repositories.sales_record_repository import SalesRecordRepository
from app.services.consolidated_data_service import ConsolidatedDataService
from app.utils.period_calendar import fy_quarter_label, fy_short


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


def _seed_mt_rows(
    db: Session,
    *,
    company: str,
    rows: list[tuple[str, float]],
) -> None:
    """Insert consolidated-style sales already stored as MT (ACTIVE = not soft-deleted)."""
    dist = Distributor(
        name=f"{company} Rep {uuid.uuid4().hex[:8]}",
        company=company,
        is_active=True,
    )
    db.add(dist)
    db.flush()
    for idx, (period, qty) in enumerate(rows):
        report = Report(
            name=f"{company}-{period}-{uuid.uuid4().hex[:6]}",
            distributor_id=dist.id,
            reporting_month=period,
            status=ReportStatus.PROCESSED.value,
            is_deleted=False,
        )
        db.add(report)
        db.flush()
        db.add(
            SalesRecord(
                report_id=report.id,
                distributor_id=dist.id,
                customer_name=f"Customer {idx}",
                segment="Paper",
                product="APCOFLEX N745",
                quantity=Decimal(str(qty)),
                unit="MT",
                original_unit="MT",
                period=period,
                row_hash=uuid.uuid4().hex,
                is_deleted=False,
            )
        )
    db.flush()


def test_quarterly_overview_sums_consolidated_mt_without_conversion(db: Session):
    company = f"QOverview MT Co {uuid.uuid4().hex[:6]}"
    _seed_mt_rows(
        db,
        company=company,
        rows=[
            ("April 2026", 10.5),
            ("May 2026", 25.0),
            ("June 2026", 22.1),
            ("July 2026", 100.0),
            ("April 2025", 40.0),
            ("May 2025", 60.0),
        ],
    )

    summaries = SalesRecordRepository(db).period_summaries(company=company)
    by_label = {s["label"]: s for s in summaries}

    q1_2627 = fy_quarter_label(2026, 1)
    q2_2627 = fy_quarter_label(2026, 2)
    q1_2526 = fy_quarter_label(2025, 1)

    print("\nPeriod | Records(reports) | Sum MT | API")
    for label in (q1_2627, q2_2627, q1_2526):
        row = by_label.get(label)
        assert row is not None, f"missing {label} in {list(by_label)}"
        print(f"{label} | {row['reportCount']} | {row['totalQuantity']} | {row['totalQuantity']}")

    assert abs(by_label[q1_2627]["totalQuantity"] - 57.6) < 0.001
    assert by_label[q1_2627]["reportCount"] == 3
    assert abs(by_label[q2_2627]["totalQuantity"] - 100.0) < 0.001
    assert abs(by_label[q1_2526]["totalQuantity"] - 100.0) < 0.001

    fy_2526_total = sum(
        float(s["totalQuantity"])
        for s in summaries
        if str(s["label"]).startswith(fy_short(2025) + " •")
    )
    print(f"FY 2025-26 | - | {fy_2526_total} | {fy_2526_total}")
    assert abs(fy_2526_total - 100.0) < 0.001

    page = ConsolidatedDataService(db).list_records(
        company=company,
        skip=0,
        limit=50,
        page_by="reports",
    )
    api_by = {s.label: float(s.totalQuantity) for s in page.periodSummaries}
    assert abs(api_by[q1_2627] - 57.6) < 0.001
    assert abs(api_by[q2_2627] - 100.0) < 0.001


def test_period_summaries_does_not_divide_large_mt_values(db: Session):
    """1000+500+250 MT must stay 1750 — never become 1.750."""
    company = f"QOverview Large MT Co {uuid.uuid4().hex[:6]}"
    _seed_mt_rows(
        db,
        company=company,
        rows=[
            ("April 2026", 1000.0),
            ("May 2026", 500.0),
            ("June 2026", 250.0),
        ],
    )
    summaries = SalesRecordRepository(db).period_summaries(company=company)
    q1 = next(s for s in summaries if s["label"] == fy_quarter_label(2026, 1))
    assert abs(q1["totalQuantity"] - 1750.0) < 0.001
    assert q1["totalQuantity"] != pytest.approx(1.75, abs=0.01)
