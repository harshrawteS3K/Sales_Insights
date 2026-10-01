"""Distributor names that differ only in formatting / legal suffix resolve to one row."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.enums import ReportStatus
from app.models.distributor import Distributor
from app.models.report import Report
from app.models.sales_record import SalesRecord
from app.repositories.distributor_repository import DistributorRepository
from app.utils.distributor_name import normalize_distributor_name


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


def _tag() -> str:
    return uuid.uuid4().hex[:6]


@pytest.mark.parametrize(
    "variant",
    [
        "Reda pvt lt",
        "REDA Private Ltd",
        "Reda Pvt Ltd",
        "Reda Pvt. Ltd.",
        "REDA PRIVATE LIMITED",
        "reda private ltd",
        "  Reda   Pvt.Ltd ",
        "Reda (P) Ltd",
        "REDA PVTLTD",
        "Reda Ltd",
        "Reda",
    ],
)
def test_legal_suffix_and_formatting_variants_share_key(variant: str):
    assert normalize_distributor_name(variant) == "REDA"


def test_genuinely_different_companies_keep_distinct_keys():
    keys = {
        normalize_distributor_name(n)
        for n in (
            "Reda Chemicals Pvt Ltd",
            "Reda Polymers Pvt Ltd",
            "Redax Pvt Ltd",
            "Reda LLP",
        )
    }
    assert len(keys) == 4
    assert normalize_distributor_name("LT Foods Pvt Ltd") == "LTFOODS"
    assert normalize_distributor_name("Private Limited") != ""


def test_reda_pvt_lt_reuses_existing_reda_private_ltd(db: Session):
    tag = _tag()
    repo = DistributorRepository(db)
    existing = repo.get_or_create_by_company(f"REDA {tag} Private Ltd")
    resolved = repo.get_or_create_by_company(f"Reda {tag} pvt lt")
    assert resolved.id == existing.id
    assert existing.company == f"REDA {tag} Private Ltd"


def test_case_spacing_punctuation_variants_resolve_same_id(db: Session):
    tag = _tag()
    repo = DistributorRepository(db)
    first = repo.get_or_create_by_company(f"Sharma {tag} Traders Pvt. Ltd.")
    for variant in (
        f"SHARMA {tag} TRADERS PVT LTD",
        f"sharma   {tag}  traders private limited",
        f"Sharma {tag} Traders (P) Ltd",
        f"Sharma {tag} Traders",
    ):
        assert repo.get_or_create_by_company(variant).id == first.id


def test_different_companies_get_different_ids(db: Session):
    tag = _tag()
    repo = DistributorRepository(db)
    a = repo.get_or_create_by_company(f"Reda {tag} Chemicals Pvt Ltd")
    b = repo.get_or_create_by_company(f"Reda {tag} Polymers Pvt Ltd")
    assert a.id != b.id


def test_repeated_submissions_do_not_create_duplicates(db: Session):
    tag = _tag()
    repo = DistributorRepository(db)
    ids = {
        repo.get_or_create_by_company(name).id
        for name in (
            f"Reda {tag} pvt lt",
            f"REDA {tag} Private Ltd",
            f"Reda {tag} pvt lt",
            f"reda {tag} PVT. LTD.",
        )
    }
    assert len(ids) == 1
    key = normalize_distributor_name(f"Reda {tag}")
    matches = [
        d
        for d in db.scalars(select(Distributor).where(Distributor.is_deleted.is_(False))).all()
        if normalize_distributor_name(d.company) == key
    ]
    assert len(matches) == 1


def test_customers_from_both_submissions_attach_to_same_distributor(db: Session):
    tag = _tag()
    repo = DistributorRepository(db)
    submissions = [
        (f"REDA {tag} Private Ltd", "Customer Alpha", "April 2026"),
        (f"Reda {tag} pvt lt", "Customer Beta", "May 2026"),
    ]
    dist_ids = []
    for company, customer, month in submissions:
        dist = repo.get_or_create_by_company(company)
        dist_ids.append(dist.id)
        report = Report(
            name=f"{company}-{uuid.uuid4().hex[:6]}",
            distributor_id=dist.id,
            reporting_month=month,
            status=ReportStatus.PROCESSED.value,
            is_deleted=False,
        )
        db.add(report)
        db.flush()
        db.add(
            SalesRecord(
                report_id=report.id,
                distributor_id=dist.id,
                customer_name=customer,
                segment="Paper",
                product="APCOFLEX N745",
                quantity=Decimal("1"),
                unit="MT",
                original_unit="MT",
                period=month,
                row_hash=uuid.uuid4().hex,
                is_deleted=False,
            )
        )
        db.flush()

    assert dist_ids[0] == dist_ids[1]
    customers = set(
        db.scalars(
            select(func.distinct(SalesRecord.customer_name)).where(
                SalesRecord.distributor_id == dist_ids[0],
                SalesRecord.is_deleted.is_(False),
            )
        ).all()
    )
    assert customers == {"Customer Alpha", "Customer Beta"}
