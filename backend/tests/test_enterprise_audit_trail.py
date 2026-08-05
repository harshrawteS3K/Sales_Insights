"""Enterprise Audit Trail — pagination, filters, immutability, event logging."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.enums import AuditAction, AuditModule, AuditStatus
from app.schemas.audit import AuditEventCreate, AuditTrailCreate
from app.services.audit_service import AuditService


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


def test_audit_log_infers_module_and_status(db: Session):
    svc = AuditService(db)
    created = svc.log(
        AuditTrailCreate(
            user_name="Harsh Rawte",
            user_role="admin",
            action=AuditAction.GENERATED,
            details="Generated distributor template (100 customers, 50 products)",
            entity_type="template",
        )
    )
    assert created.module == AuditModule.MASTER_DATA.value
    assert created.status == AuditStatus.SUCCESS.value
    assert created.user_role == "admin"


def test_audit_list_page_server_side_search_and_pagination(db: Session):
    svc = AuditService(db)
    for i in range(12):
        svc.record(
            actor="Test Admin",
            role="admin",
            action=AuditAction.UPLOADED,
            description=f"UniqueAuditMarker customer master batch {i}",
            module=AuditModule.MASTER_DATA.value,
            entity_type="customer_master",
        )

    page1 = svc.list_page(page=1, page_size=5, search="UniqueAuditMarker")
    assert page1.total >= 12
    assert len(page1.data) == 5
    assert page1.page == 1
    assert page1.totalPages >= 3

    page2 = svc.list_page(page=2, page_size=5, search="UniqueAuditMarker")
    assert len(page2.data) == 5
    assert page2.data[0].id != page1.data[0].id

    filtered = svc.list_page(
        page=1,
        page_size=50,
        search="UniqueAuditMarker",
        module=AuditModule.MASTER_DATA.value,
        role="admin",
        status=AuditStatus.SUCCESS.value,
    )
    assert filtered.total >= 12
    assert all(r.module == AuditModule.MASTER_DATA.value for r in filtered.data)


def test_audit_get_detail(db: Session):
    svc = AuditService(db)
    created = svc.record(
        actor="Rajesh Kumar",
        role="user",
        action=AuditAction.OPENED,
        description="Opened Visualizations",
        module=AuditModule.VISUALIZATION.value,
        status=AuditStatus.INFO.value,
        metadata={"tab": "products"},
    )
    fetched = svc.get(created.id)
    assert fetched.id == created.id
    row = svc.to_row(fetched)
    assert row.description == "Opened Visualizations"
    assert row.metadata == {"tab": "products"}


def test_client_event_login(db: Session):
    svc = AuditService(db)
    created = svc.log_client_event(
        AuditEventCreate(
            action="Admin Login",
            module="Authentication",
            description="Debabrata C signed in as admin",
            status="Info",
            entity_type="auth",
        ),
        actor="Debabrata C",
        role="admin",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    assert created.module == "Authentication"
    assert created.ip_address == "127.0.0.1"
    assert created.status == "Info"


def test_audit_export_excel(db: Session, tmp_path):
    svc = AuditService(db)
    svc.record(
        actor="Export Tester",
        action=AuditAction.EXPORTED,
        description="ExportAuditMarker row",
        module=AuditModule.SYSTEM.value,
    )
    path = svc.export_excel(search="ExportAuditMarker", max_rows=100)
    assert path.exists()
    assert path.suffix == ".xlsx"
    assert path.stat().st_size > 0


def test_failed_action_infers_failed_status(db: Session):
    svc = AuditService(db)
    created = svc.log(
        AuditTrailCreate(
            user_name="system",
            action=AuditAction.FAILED,
            details="Outlook sync failed",
            entity_type="sync_job",
        )
    )
    assert created.status == AuditStatus.FAILED.value
    assert created.module == AuditModule.EMAILS.value
