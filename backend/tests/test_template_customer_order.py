"""Regression: all-history customer dropdown; latest quarter first."""

from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.repositories.distributor_customer_mapping_repository import (
    DistributorCustomerMappingRepository,
)
from app.repositories.distributor_repository import DistributorRepository
from app.schemas.distributor import TemplateGenerateRequest
from app.services.master_data_service import MasterDataService
from app.services.product_master_service import ProductMasterService
from app.services.report_service import ReportService
from app.services.template_generation_service import TemplateGenerationService
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


def _seed_products(db: Session) -> None:
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


def _ingest(
    db: Session,
    tmp_path: Path,
    *,
    company: str,
    quarter: str,
    customers: list[str],
    tag: str,
) -> None:
    rows = [(i + 1, name, "Paper", "P1", 10) for i, name in enumerate(customers)]
    path = build_official_workbook(
        tmp_path / f"{tag}.xlsx",
        distributor="Rep Order",
        company=company,
        reporting_month=quarter,
        rows=rows,
    )
    ReportService(db).ingest_excel(path, actor="tester")


def _customer_list_order(xlsx_path: Path) -> list[str]:
    wb = load_workbook(xlsx_path)
    assert "CustomerList" in wb.sheetnames
    sheet = wb["CustomerList"]
    values: list[str] = []
    for r in range(1, sheet.max_row + 1):
        raw = sheet.cell(row=r, column=1).value
        if raw is None:
            continue
        text = str(raw).strip()
        if not text or text.casefold() in {"customers", "customer", "customer name"}:
            continue
        values.append(text)
    return values


def test_latest_quarter_customers_first_without_reporting_quarter(
    db: Session, tmp_path: Path
):
    _seed_products(db)
    company = _uid("Hist")
    _ingest(db, tmp_path, company=company, quarter="Q1 2091", customers=["AKS RUGS"], tag="q1")
    _ingest(
        db,
        tmp_path,
        company=company,
        quarter="Q2 2091",
        customers=["XYZ POLYMERS", "ABC TRADERS"],
        tag="q2",
    )
    dist = DistributorRepository(db).get_by_company(company)
    assert dist is not None

    names = DistributorCustomerMappingRepository(db).list_names_for_template(dist.id)
    assert [n.casefold() for n in names] == [
        "abc traders",
        "xyz polymers",
        "aks rugs",
    ]

    out = tmp_path / "tpl.xlsx"
    result = TemplateGenerationService(db).generate(
        actor="tester",
        mode="distributor",
        distributor_id=dist.id,
        reporting_quarter=None,
        output_path=out,
        update_canonical=False,
    )
    assert result.fallback_generic is False
    assert result.customers_count == 3
    assert [n.casefold() for n in _customer_list_order(out)] == [
        "abc traders",
        "xyz polymers",
        "aks rugs",
    ]


def test_q4_to_q1_next_fy_latest_first(db: Session, tmp_path: Path):
    _seed_products(db)
    company = _uid("FY")
    _ingest(db, tmp_path, company=company, quarter="Q2 2090", customers=["AKS RUGS"], tag="q2")
    _ingest(
        db,
        tmp_path,
        company=company,
        quarter="Q4 2090",
        customers=["PQR INDUSTRIES"],
        tag="q4",
    )
    dist = DistributorRepository(db).get_by_company(company)
    assert dist is not None
    names = DistributorCustomerMappingRepository(db).list_names_for_template(dist.id)
    assert [n.casefold() for n in names] == ["pqr industries", "aks rugs"]


def test_single_quarter_history_included_without_quarter_input(
    db: Session, tmp_path: Path
):
    """Demo-style case: only one imported quarter → still populate dropdown."""
    _seed_products(db)
    company = _uid("Demo")
    _ingest(
        db,
        tmp_path,
        company=company,
        quarter="Q2 2026",
        customers=["AKS RUGS"],
        tag="demo",
    )
    dist = DistributorRepository(db).get_by_company(company)
    assert dist is not None

    result = TemplateGenerationService(db).generate(
        actor="tester",
        mode="distributor",
        distributor_id=dist.id,
        reporting_quarter=None,
        output_path=tmp_path / "demo.xlsx",
        update_canonical=False,
    )
    assert result.fallback_generic is False
    assert result.customers_count == 1
    assert any(n.casefold() == "aks rugs" for n in _customer_list_order(tmp_path / "demo.xlsx"))


def test_master_data_does_not_require_reporting_quarter(db: Session, tmp_path: Path):
    _seed_products(db)
    company = _uid("NoQ")
    _ingest(db, tmp_path, company=company, quarter="Q1 2088", customers=["CUST A"], tag="q")
    dist = DistributorRepository(db).get_by_company(company)
    assert dist is not None
    result = MasterDataService(db).generate_template(
        actor="admin",
        request=TemplateGenerateRequest(mode="distributor", distributor_id=dist.id),
    )
    assert result.success
    assert result.customers_count >= 1
    assert result.fallback_generic is False


def test_no_history_falls_back_to_generic(db: Session, tmp_path: Path):
    _seed_products(db)
    from app.schemas.distributor import DistributorCreate
    from app.services.distributor_service import DistributorService

    dist = DistributorService(db).create_distributor(
        DistributorCreate(
            name=_uid("Empty"),
            company=_uid("Empty Co"),
            email=f"{uuid4().hex[:8]}@example.com",
        ),
        actor="admin",
    )
    out = tmp_path / "empty.xlsx"
    result = TemplateGenerationService(db).generate(
        actor="tester",
        mode="distributor",
        distributor_id=dist.id,
        output_path=out,
        update_canonical=False,
    )
    assert result.fallback_generic is True
    assert result.customers_count == 0
    assert "No customer history" in (result.warning or "")
    wb = load_workbook(out)
    assert "CustomerList" not in wb.sheetnames
