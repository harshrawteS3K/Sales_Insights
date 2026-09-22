"""Unit tests for Bulk Persona Import Service & API Endpoints."""

import pytest
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.user import User
from app.models.distributor import Distributor
from app.models.user_distributor import UserDistributor
from app.models.user_segment import UserSegment
from app.services.bulk_persona_import_service import BulkPersonaImportService
from app.enums import UserRole


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
def sample_excel_file(tmp_path):
    from uuid import uuid4

    suffix = uuid4().hex[:6]
    excel_file = tmp_path / "test_distributors.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    owner_a = f"Anup Pandey {suffix}"
    owner_b = f"Sachin Kasar {suffix}"
    ws.append(["Second Party", "Owner", "Segment"])
    ws.append([f"Reda Industries {suffix}", owner_a, "Construction"])
    ws.append([f"Altek {suffix}", owner_b, "Rubber"])
    ws.append([f"Behn Meyr {suffix}", owner_b, "Rubber"])

    wb.save(excel_file)
    return excel_file, owner_a, owner_b, suffix


def test_bulk_persona_import_preview(db: Session, sample_excel_file):
    excel_file, owner_a, owner_b, _suffix = sample_excel_file
    service = BulkPersonaImportService(db)
    preview = service.preview_import(excel_file)

    assert preview["total_rows"] == 3
    assert preview["unique_owners"] == 2
    assert owner_a in preview["new_users"]
    assert owner_b in preview["new_users"]
    assert set(preview["distinct_segments"]) == {"Construction", "Rubber"}


def test_bulk_persona_import_execution(db: Session, sample_excel_file):
    excel_file, owner_a, owner_b, suffix = sample_excel_file
    service = BulkPersonaImportService(db)
    result = service.execute_import(excel_file, replace_existing=False, actor="admin_test")

    assert result["success"] is True
    assert result["total_records"] == 3
    assert len(result["created_users"]) == 2

    db.expire_all()

    # Verify created users
    anup = db.query(User).filter(User.full_name == owner_a).first()
    assert anup is not None
    assert anup.username.startswith("anup")
    assert anup.role == UserRole.USER.value

    sachin = db.query(User).filter(User.full_name == owner_b).first()
    assert sachin is not None
    assert sachin.username.startswith("sachin")

    # Verify distributors (company may be title-cased / whitespace-normalized)
    altek = (
        db.query(Distributor)
        .filter(Distributor.company.ilike(f"%Altek%{suffix}%"), Distributor.is_deleted.is_(False))
        .first()
    )
    assert altek is not None

    # Verify user distributor assignment
    sachin_ud = db.query(UserDistributor).filter(
        UserDistributor.user_id == sachin.id,
        UserDistributor.distributor_id == altek.id,
    ).first()
    assert sachin_ud is not None

    # Verify user segment assignment
    sachin_us = db.query(UserSegment).filter(
        UserSegment.user_id == sachin.id,
        UserSegment.segment == "Rubber",
    ).first()
    assert sachin_us is not None
