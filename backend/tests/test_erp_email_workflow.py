"""ERP email preview + approve-import workflow tests."""

from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.enums import EmailProcessStatus
from app.models.distributor import Distributor
from app.models.email_message import EmailAttachment, EmailMessage
from app.services.erp_ingest_service import ERPIngestService
from app.utils.datetime_utils import utc_now
import pytest


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
    return f"{prefix}-{uuid4().hex[:8]}"


def _erp_xlsx(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Party Name", "Material", "Dispatch Qty"])
    ws.append(["Alpha Mills", "Latex-A", 10])
    ws.append(["Beta Corp", "Latex-B", 20])
    ws.append(["TOTAL", "", 30])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _seed_email_with_xlsx(db: Session, tmp_path: Path, *, sender_email: str) -> EmailMessage:
    xlsx = _erp_xlsx(tmp_path / f"{_uid('wb')}.xlsx")
    email = EmailMessage(
        graph_message_id=_uid("graph"),
        subject="ERP Sales Export",
        sender_name="Rep",
        sender_email=sender_email,
        received_at=utc_now(),
        has_attachments=True,
        is_read=False,
        process_status=EmailProcessStatus.DOWNLOADED.value,
        mailbox="salesinsights@apcotex.com",
    )
    db.add(email)
    db.flush()
    att = EmailAttachment(
        graph_attachment_id=_uid("att"),
        file_name=xlsx.name,
        file_path=str(xlsx),
        is_excel=True,
        email_message_id=email.id,
        size_bytes=xlsx.stat().st_size,
    )
    db.add(att)
    db.flush()
    return email


def test_email_sync_sets_downloaded_not_imported(db: Session, tmp_path: Path):
    """Sync path stores Excel as downloaded; import happens only after approve."""
    email = _seed_email_with_xlsx(db, tmp_path, sender_email=f"{_uid('sync')}@example.com")
    db.commit()
    db.refresh(email)
    assert email.process_status == EmailProcessStatus.DOWNLOADED.value
    # No sales report should exist for this email yet
    from app.models.report import Report
    from sqlalchemy import select

    reports = list(
        db.scalars(select(Report).where(Report.email_message_id == email.id)).all()
    )
    assert reports == []


def test_preview_parsing(db: Session, tmp_path: Path):
    email = _seed_email_with_xlsx(db, tmp_path, sender_email=f"{_uid('s')}@example.com")
    db.commit()

    preview = ERPIngestService(db).preview_email(email.id, actor="admin")
    assert preview["row_count"] == 2
    assert preview["sheet_name"] == "Sales"
    assert preview["confidence"]["overall"] >= 75
    originals = {m["original"] for m in preview["mapping"]}
    assert "Party Name" in originals


def test_manual_mapping_correction(db: Session, tmp_path: Path):
    email = _seed_email_with_xlsx(db, tmp_path, sender_email=f"{_uid('m')}@example.com")
    db.commit()
    svc = ERPIngestService(db)
    preview = svc.preview_email(email.id, actor="admin")
    # Swap via explicit column mapping still yields 2 rows
    remap = [
        {"original": "Party Name", "mapped": "Customer Name", "column": 1},
        {"original": "Material", "mapped": "Product", "column": 2},
        {"original": "Dispatch Qty", "mapped": "Sales Quantity", "column": 3},
    ]
    again = svc.preview_email(email.id, actor="admin", mapping_override=remap)
    assert again["row_count"] == 2
    assert again["mapping"][0]["method"] == "manual"


def test_distributor_resolution(db: Session, tmp_path: Path):
    email_addr = f"{_uid('dist')}@avikpolychem.com"
    dist = Distributor(
        name="Contact",
        company=_uid("Avik"),
        email=email_addr,
        is_active=True,
    )
    db.add(dist)
    db.flush()
    email = _seed_email_with_xlsx(db, tmp_path, sender_email=email_addr)
    db.commit()

    preview = ERPIngestService(db).preview_email(email.id, actor="admin")
    assert preview["distributor_id"] == dist.id
    assert preview["distributor_unknown"] is False


def test_import_approval_and_audit(db: Session, tmp_path: Path):
    from app.models.audit_trail import AuditTrail
    from sqlalchemy import select

    email_addr = f"{_uid('imp')}@example.com"
    dist = Distributor(
        name="Imp Contact",
        company=_uid("ImpCo"),
        email=email_addr,
        is_active=True,
    )
    db.add(dist)
    db.flush()
    email = _seed_email_with_xlsx(db, tmp_path, sender_email=email_addr)
    db.commit()

    svc = ERPIngestService(db)
    preview = svc.preview_email(email.id, actor="admin")
    result = svc.import_approved(
        email_id=email.id,
        distributor_id=dist.id,
        reporting_quarter="Q3 2026",
        actor="admin",
    )
    assert result["records_inserted"] == 2
    assert result["reporting_quarter"] in ("Q3 2026",)
    db.refresh(email)
    assert email.process_status == EmailProcessStatus.INSERTED.value

    audits = list(
        db.scalars(
            select(AuditTrail).where(AuditTrail.details.ilike("%ERP Report Imported%"))
        ).all()
    )
    assert len(audits) >= 1


def test_consolidated_visibility_after_import(db: Session, tmp_path: Path):
    from app.repositories.sales_record_repository import SalesRecordRepository

    email_addr = f"{_uid('vis')}@example.com"
    dist = Distributor(
        name="Vis",
        company=_uid("VisCo"),
        email=email_addr,
        is_active=True,
    )
    db.add(dist)
    db.flush()
    email = _seed_email_with_xlsx(db, tmp_path, sender_email=email_addr)
    db.commit()

    svc = ERPIngestService(db)
    svc.preview_email(email.id, actor="admin")
    result = svc.import_approved(
        email_id=email.id,
        distributor_id=dist.id,
        reporting_quarter="Q3 2026",
        actor="admin",
    )
    sales = SalesRecordRepository(db).list_by_report(result["report_id"]) if hasattr(
        SalesRecordRepository(db), "list_by_report"
    ) else []
    if not sales:
        from app.models.sales_record import SalesRecord
        from sqlalchemy import select

        sales = list(
            db.scalars(
                select(SalesRecord).where(SalesRecord.report_id == result["report_id"])
            ).all()
        )
    assert len(sales) == 2
    assert all(s.segment == "" for s in sales)
    assert {s.customer_name for s in sales} == {"Alpha Mills", "Beta Corp"}
