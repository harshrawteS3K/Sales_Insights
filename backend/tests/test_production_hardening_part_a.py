"""Part A production hardening regression tests (bugs 1–6)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.enums import EmailProcessStatus, ReportSource
from app.exceptions import ValidationAppError
from app.models.email_message import EmailMessage
from app.repositories.distributor_repository import DistributorRepository
from app.repositories.email_repository import EmailMessageRepository
from app.repositories.sales_record_repository import SalesRecordRepository
from app.schemas.report import ReportCreate
from app.services.outlook_sync_service import OutlookSyncService
from app.services.report_service import ReportService
from app.utils.distributor_name import normalize_distributor_name
from app.utils.datetime_utils import utc_now
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


def test_normalize_distributor_name():
    assert normalize_distributor_name("  Navneet   Goel ") == "Navneet Goel"
    assert normalize_distributor_name("ACME") == "ACME"


def test_bug2_distributor_case_insensitive_match(db: Session):
    repo = DistributorRepository(db)
    a = repo.get_or_create_by_name("Navneet Goel")
    b = repo.get_or_create_by_name("  NAVNEET   GOEL  ")
    assert a.id == b.id
    assert a.name == "Navneet Goel"


def test_bug2_report_replacement_same_distributor_month(db: Session, tmp_path: Path):
    svc = ReportService(db)
    company = "Replace Dist Co Identity"
    path1 = build_official_workbook(
        tmp_path / "r1.xlsx",
        distributor="Replace Dist Co",
        company=company,
        reporting_month="July 2026",
        rows=[(1, "Cust A", "Paper", "PROD-1", 10, 1, 2)],
    )
    path2 = build_official_workbook(
        tmp_path / "r2.xlsx",
        distributor="replace dist co",  # different casing on representative
        company=company,
        reporting_month="July 2026",
        rows=[(1, "Cust B", "Paper", "PROD-2", 20, 3, 4)],
    )
    r1, n1, _, _ = svc.ingest_excel(path1, source=ReportSource.UPLOAD, actor="test")
    assert n1 == 1
    r2, n2, _, _ = svc.ingest_excel(path2, source=ReportSource.UPLOAD, actor="test")
    assert n2 == 1
    db.refresh(r1)
    db.refresh(r2)
    assert r1.is_deleted is True
    assert r2.is_deleted is False
    assert r1.distributor_id == r2.distributor_id
    sales = SalesRecordRepository(db)
    assert sales.count_active_for_report(r1.id) == 0
    assert sales.count_active_for_report(r2.id) == 1


def test_bug5_ghost_report_blocked(db: Session):
    svc = ReportService(db)
    with pytest.raises(ValidationAppError):
        svc.create_report(
            ReportCreate(name="Ghost", distributor_id=None, reporting_month=None),
            actor="test",
        )


def test_bug4_period_count_uses_reporting_month(db: Session, tmp_path: Path):
    svc = ReportService(db)
    path = build_official_workbook(
        tmp_path / "p.xlsx",
        distributor="Period Dist",
        reporting_month="August 2026",
        rows=[(1, "Cust", "Carpet", "P1", 5, 0, 0)],
    )
    report, _, _, _ = svc.ingest_excel(path, source=ReportSource.UPLOAD, actor="test")
    # Sales period may be null; count must still find via report.reporting_month
    count = SalesRecordRepository(db).count_by_distributor_period("Period Dist", "August 2026")
    assert count >= 1
    assert report.reporting_month == "August 2026"


def test_bug1_already_processed_retries_mark_as_read(db: Session):
    emails = EmailMessageRepository(db)
    email = emails.create(
        EmailMessage(
            graph_message_id="graph-msg-retry-1",
            internet_message_id="<retry@test.local>",
            subject="Already done",
            sender_email="a@b.com",
            received_at=utc_now(),
            process_status=EmailProcessStatus.INSERTED.value,
            is_read=False,
            has_attachments=True,
            mailbox="test@apcotex.com",
        )
    )
    graph = MagicMock()
    graph.mark_as_read = MagicMock()
    graph.resolve_mailbox = MagicMock(return_value="test@apcotex.com")
    svc = OutlookSyncService(db, graph_client=graph)

    result = svc._process_message(
        {"id": "graph-msg-retry-1", "internetMessageId": "<retry@test.local>"},
        mailbox="test@apcotex.com",
        mark_as_read=True,
        actor="test",
    )
    assert result["status"] == "already_processed"
    graph.mark_as_read.assert_called_once_with("graph-msg-retry-1", mailbox="test@apcotex.com")
    db.refresh(email)
    assert email.is_read is True
    assert email.process_status == EmailProcessStatus.MARKED_READ.value


def test_bug3_dedupe_by_internet_message_id(db: Session):
    emails = EmailMessageRepository(db)
    first = emails.create(
        EmailMessage(
            graph_message_id="graph-old-id",
            internet_message_id="<same-internet@id>",
            subject="One",
            sender_email="a@b.com",
            received_at=utc_now(),
            process_status=EmailProcessStatus.MARKED_READ.value,
            is_read=True,
            has_attachments=True,
            mailbox="test@apcotex.com",
        )
    )
    graph = MagicMock()
    graph.mark_as_read = MagicMock()
    svc = OutlookSyncService(db, graph_client=graph)
    result = svc._process_message(
        {
            "id": "graph-new-id",  # Graph id changed
            "internetMessageId": "<same-internet@id>",
        },
        mailbox="test@apcotex.com",
        mark_as_read=True,
        actor="test",
    )
    assert result["status"] == "already_processed"
    db.refresh(first)
    assert first.graph_message_id == "graph-new-id"
    graph.mark_as_read.assert_called_once()


def test_bug1_skipped_marks_read(db: Session):
    graph = MagicMock()
    graph.list_attachments = MagicMock(return_value=[{"id": "a1", "name": "note.txt", "contentType": "text/plain"}])
    graph.mark_as_read = MagicMock()
    graph.is_excel_attachment = staticmethod(lambda a: False)
    # Use real is_excel_attachment from GraphClient - patch list to return non-excel
    from app.integrations.graph.client import GraphClient

    graph.is_excel_attachment = GraphClient.is_excel_attachment

    svc = OutlookSyncService(db, graph_client=graph)
    result = svc._process_message(
        {
            "id": "graph-skip-1",
            "internetMessageId": "<skip@test>",
            "subject": "No excel",
            "from": {"emailAddress": {"name": "X", "address": "x@y.com"}},
            "receivedDateTime": "2026-07-01T10:00:00Z",
            "hasAttachments": True,
        },
        mailbox="test@apcotex.com",
        mark_as_read=True,
        actor="test",
    )
    assert result["status"] == "skipped_no_excel"
    graph.mark_as_read.assert_called_once()
    email = EmailMessageRepository(db).get_by_graph_id("graph-skip-1")
    assert email is not None
    assert email.process_status == EmailProcessStatus.SKIPPED.value
    assert email.is_read is True
