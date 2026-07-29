"""Phase 2 Master Data Engine regression tests."""

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.exceptions import ExcelProcessingError, ValidationAppError
from app.integrations.excel.parser import ExcelParserService
from app.integrations.excel.template_generator import ExcelTemplateGenerator
from app.repositories.master_repository import CustomerMasterRepository, ProductMasterRepository
from app.services.customer_master_service import CustomerMasterService
from app.services.product_master_service import ProductMasterService
from app.services.template_generation_service import TemplateGenerationService
from app.validators.excel_validators import (
    validate_customer_master_dataframe,
    validate_product_master_dataframe,
)
import pandas as pd


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


def _write_customer_master(path: Path, names: list[str], *, header: str = "CUSTOMER NAME") -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append([header, "REGION"])
    for name in names:
        ws.append([name, "West"])
    wb.save(path)
    return path


def _write_product_master(
    path: Path,
    rows: list[tuple[str, str]],
    *,
    industry_header: str = "Industry Type Description",
    code_header: str = "Product Code",
) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append([industry_header, code_header])
    for industry, code in rows:
        ws.append([industry, code])
    wb.save(path)
    return path


class _Upload:
    """Minimal UploadFile-like object for service tests."""

    def __init__(self, path: Path) -> None:
        self.filename = path.name
        self._path = path
        self._fh = None

    async def read(self, size: int = -1) -> bytes:
        if self._fh is None:
            self._fh = self._path.open("rb")
        if size < 0:
            data = self._fh.read()
        else:
            data = self._fh.read(size)
        return data

    async def seek(self, offset: int) -> None:
        if self._fh is None:
            self._fh = self._path.open("rb")
        self._fh.seek(offset)


@pytest.mark.asyncio
async def test_scenario1_upload_customer_master_1000(db: Session, tmp_path: Path):
    names = [f"Customer {i:04d}" for i in range(1000)]
    path = _write_customer_master(tmp_path / "customers.xlsx", names)
    svc = CustomerMasterService(db)
    result = await svc.upload_and_replace(_Upload(path), actor="test")
    assert result.success
    assert result.records_imported == 1000
    assert CustomerMasterRepository(db).count() == 1000


@pytest.mark.asyncio
async def test_scenario2_upload_product_master_200(db: Session, tmp_path: Path):
    rows = [(f"INDUSTRY {i % 10}", f"PROD-{i:04d}") for i in range(200)]
    path = _write_product_master(tmp_path / "products.xlsx", rows)
    svc = ProductMasterService(db)
    result = await svc.upload_and_replace(_Upload(path), actor="test")
    assert result.success
    assert result.records_imported == 200
    assert ProductMasterRepository(db).count() == 200


@pytest.mark.asyncio
async def test_scenario3_generate_template_dropdowns(db: Session, tmp_path: Path):
    cust_path = _write_customer_master(tmp_path / "c.xlsx", ["Alpha Co", "Beta Co", "Zeta Co"])
    prod_path = _write_product_master(
        tmp_path / "p.xlsx",
        [("PAPER", "FGC8200-200"), ("CARPET", "FGCB200-200")],
    )
    await CustomerMasterService(db).upload_and_replace(_Upload(cust_path), actor="test")
    await ProductMasterService(db).upload_and_replace(_Upload(prod_path), actor="test")

    out = tmp_path / "template.xlsx"
    ExcelTemplateGenerator().generate(
        customers=CustomerMasterRepository(db).list_names(),
        products=ProductMasterRepository(db).list_product_codes(),
        output_path=out,
    )
    wb = load_workbook(out)
    assert "Sales Report" in wb.sheetnames
    assert "_lists" in wb.sheetnames
    lists = wb["_lists"]
    assert lists.sheet_state == "hidden"
    customers = [lists["A2"].value, lists["A3"].value, lists["A4"].value]
    assert customers == ["Alpha Co", "Beta Co", "Zeta Co"]
    products = [lists["B2"].value, lists["B3"].value]
    assert products == ["FGCB200-200", "FGC8200-200"] or set(products) == {
        "FGC8200-200",
        "FGCB200-200",
    }
    # Headers include Customer + Product for dropdowns
    sheet = wb["Sales Report"]
    headers = [sheet.cell(7, c).value for c in range(1, 8)]
    assert headers == [
        "Sr. No.",
        "Name of Customer",
        "Segment",
        "Product",
        "Opening Stock",
        "Closing Stock",
        "Quantity",
    ]
    assert len(sheet.data_validations.dataValidation) >= 2


@pytest.mark.asyncio
async def test_scenario4_customer_master_replace(db: Session, tmp_path: Path):
    svc = CustomerMasterService(db)
    await svc.upload_and_replace(
        _Upload(_write_customer_master(tmp_path / "c1.xlsx", ["Old A", "Old B"])),
        actor="test",
    )
    assert set(CustomerMasterRepository(db).list_names()) == {"Old A", "Old B"}

    await svc.upload_and_replace(
        _Upload(_write_customer_master(tmp_path / "c2.xlsx", ["New X", "New Y", "New Z"])),
        actor="test",
    )
    names = CustomerMasterRepository(db).list_names()
    assert set(names) == {"New X", "New Y", "New Z"}
    assert CustomerMasterRepository(db).count() == 3


@pytest.mark.asyncio
async def test_scenario5_product_master_replace(db: Session, tmp_path: Path):
    svc = ProductMasterService(db)
    await svc.upload_and_replace(
        _Upload(_write_product_master(tmp_path / "p1.xlsx", [("PAPER", "OLD-1"), ("PAPER", "OLD-2")])),
        actor="test",
    )
    await svc.upload_and_replace(
        _Upload(
            _write_product_master(
                tmp_path / "p2.xlsx",
                [("CARPET", "NEW-A"), ("CONSTRUCTION B2B IH", "NEW-B")],
            )
        ),
        actor="test",
    )
    codes = ProductMasterRepository(db).list_product_codes()
    assert set(codes) == {"NEW-A", "NEW-B"}
    assert ProductMasterRepository(db).count() == 2


def test_scenario6_invalid_excel_extension(tmp_path: Path):
    from app.services.excel_validation_service import ExcelValidationService

    with pytest.raises(ExcelProcessingError):
        ExcelValidationService().assert_excel_file("master.csv")


def test_scenario7_missing_required_header(tmp_path: Path):
    # Customer master without CUSTOMER NAME
    bad_c = tmp_path / "bad_c.xlsx"
    wb = Workbook()
    wb.active.append(["Region", "City"])
    wb.active.append(["West", "Pune"])
    wb.save(bad_c)
    df = pd.read_excel(bad_c)
    with pytest.raises(ExcelProcessingError) as exc:
        validate_customer_master_dataframe(df)
    assert "missing required columns" in str(exc.value).lower() or "customer_name" in str(exc.value)

    # Product master missing Product Code
    bad_p = tmp_path / "bad_p.xlsx"
    wb = Workbook()
    wb.active.append(["Industry Type Description"])
    wb.active.append(["PAPER"])
    wb.save(bad_p)
    dfp = pd.read_excel(bad_p)
    with pytest.raises(ExcelProcessingError):
        validate_product_master_dataframe(dfp)


def test_parser_dedupes_and_trims(tmp_path: Path):
    path = _write_customer_master(
        tmp_path / "dup.xlsx",
        ["  Acme  ", "Acme", "Beta", "", "beta"],
    )
    rows, dups = ExcelParserService().parse_customer_master(path)
    names = [r["customer_name"] for r in rows]
    assert names == ["Acme", "Beta"]
    assert dups == 2


@pytest.mark.asyncio
async def test_generate_requires_masters(db: Session):
    # Clear via replace with empty is not allowed by parser; soft-delete manually
    CustomerMasterRepository(db).soft_delete_all_active()
    ProductMasterRepository(db).soft_delete_all_active()
    svc = TemplateGenerationService(db)
    with pytest.raises(ValidationAppError):
        svc.generate(actor="test")


@pytest.mark.asyncio
async def test_bulk_replace_5000_customers_efficient(db: Session, tmp_path: Path):
    """Scale smoke: 5000 customers replace via bulk_insert_mappings."""
    names = [f"Bulk Customer {i:05d}" for i in range(5000)]
    path = _write_customer_master(tmp_path / "c5k.xlsx", names)
    svc = CustomerMasterService(db)
    result = await svc.upload_and_replace(_Upload(path), actor="test")
    assert result.success
    assert result.records_imported == 5000
    assert CustomerMasterRepository(db).count() == 5000
    assert result.processing_time_ms > 0


@pytest.mark.asyncio
async def test_advisory_lock_serializes_replace(db: Session):
    """Advisory lock helper is callable within the session transaction."""
    from app.utils.db_locks import CUSTOMER_MASTER_REPLACE_LOCK, acquire_xact_lock

    acquire_xact_lock(db, CUSTOMER_MASTER_REPLACE_LOCK, label="test")
    CustomerMasterRepository(db).replace_all(["Lock Test A", "Lock Test B"])
    assert set(CustomerMasterRepository(db).list_names()) == {"Lock Test A", "Lock Test B"}
