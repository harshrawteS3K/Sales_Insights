"""Phase-2 distributor customer mapping + template package regression."""

from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.distributor_customer_mapping import DistributorCustomerMapping
from app.schemas.distributor import DistributorCreate, TemplateGenerateRequest
from app.services.distributor_service import DistributorService
from app.services.email_package_service import EmailPackageService
from app.services.master_data_service import MasterDataService
from app.services.product_master_service import ProductMasterService
from app.services.report_service import ReportService
from app.utils.customer_name import normalize_customer_name
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


def _seed_products(db: Session, tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "pm.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Industry Type Description", "Product"])
    ws.append(["Paper", "P1"])
    ws.append(["Paper", "P2"])
    wb.save(path)
    # Prefer service replace if available
    try:
        ProductMasterService(db).replace_from_rows(
            [("Paper", "P1"), ("Paper", "P2")], actor="test"
        )
    except Exception:
        from app.models.product_master import ProductMaster

        for industry, code in [("Paper", "P1"), ("Paper", "P2")]:
            db.add(
                ProductMaster(
                    industry_type=industry,
                    product_code=code,
                    is_active=True,
                )
            )
        db.flush()


def test_normalize_customer_name():
    assert normalize_customer_name("  AKS   RUGS ") == "AKS RUGS"


def test_auto_learn_customers_on_import(db: Session, tmp_path: Path):
    company = _uid("Learn Co")
    path = build_official_workbook(
        tmp_path / "learn.xlsx",
        distributor="Rep Learn",
        company=company,
        reporting_month="Q1 2099",
        rows=[
            (1, "AKS RUGS", "Paper", "P1", 10),
            (2, "XYZ POLYMERS", "Paper", "P1", 20),
            (3, "aks rugs", "Paper", "P1", 5),  # duplicate case
        ],
    )
    report, inserted, _, _ = ReportService(db).ingest_excel(path, actor="tester")
    assert inserted >= 2
    assert report.distributor_id is not None

    names = DistributorService(db).list_customers(report.distributor_id)
    assert "AKS RUGS" in names or any(n.casefold() == "aks rugs" for n in names)
    assert any(n.casefold() == "xyz polymers" for n in names)
    # case-insensitive uniqueness → not two AKS rows
    aks = [n for n in names if n.casefold() == "aks rugs"]
    assert len(aks) == 1


def test_customer_isolation_between_distributors(db: Session, tmp_path: Path):
    a = _uid("Iso A")
    b = _uid("Iso B")
    for company, cust in [(a, "ONLY A CUST"), (b, "ONLY B CUST")]:
        path = build_official_workbook(
            tmp_path / f"{company}.xlsx",
            distributor=f"Rep {company}",
            company=company,
            reporting_month="Q1 2098",
            rows=[(1, cust, "Paper", "P1", 10)],
        )
        ReportService(db).ingest_excel(path, actor="tester")

    svc = DistributorService(db)
    from app.repositories.distributor_repository import DistributorRepository

    dist_a = DistributorRepository(db).get_by_company(a)
    dist_b = DistributorRepository(db).get_by_company(b)
    assert dist_a and dist_b
    names_a = svc.list_customers(dist_a.id)
    names_b = svc.list_customers(dist_b.id)
    assert any(n.casefold() == "only a cust" for n in names_a)
    assert not any(n.casefold() == "only b cust" for n in names_a)
    assert any(n.casefold() == "only b cust" for n in names_b)


def test_eml_contains_attachment_and_draft_flag(tmp_path: Path):
    excel = tmp_path / "t.xlsx"
    excel.write_bytes(b"PK\x03\x04fake")
    eml = EmailPackageService().build_eml_bytes(
        to_email="dist@example.com",
        cc_email="cc@example.com",
        contact_person="Navneet",
        reporting_quarter="Q2 2026",
        excel_path=excel,
        excel_filename="Apcotex_Demo_Q2_2026.xlsx",
    )
    text = eml.decode("utf-8", errors="ignore")
    assert "X-Unsent: 1" in text
    assert "dist@example.com" in text
    assert "Q2 2026" in text
    assert "Apcotex_Demo_Q2_2026.xlsx" in text


def test_create_distributor_with_new_fields(db: Session):
    svc = DistributorService(db)
    created = svc.create_distributor(
        DistributorCreate(
            name=_uid("Contact"),
            company=_uid("Company"),
            code=f"C{uuid4().hex[:6]}",
            contact_person="Person One",
            email=f"{uuid4().hex[:8]}@example.com",
            cc_email=f"cc{uuid4().hex[:6]}@example.com",
        ),
        actor="admin",
    )
    assert created.contact_person == "Person One"
    assert created.code
    assert created.cc_email
