"""Regression: mark-as-read must not roll back successful Outlook ingest."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.enums import EmailProcessStatus, ReportSource, SyncStatus
from app.exceptions import GraphAPIError
from app.models.email_message import EmailMessage
from app.models.report import Report
from app.repositories.email_repository import EmailMessageRepository
from app.schemas.email import OutlookSyncRequest
from app.services.outlook_sync_service import OutlookSyncService
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


def _graph_message(msg_id: str, *, internet_id: str, subject: str = "Sales") -> dict:
    return {
        "id": msg_id,
        "internetMessageId": internet_id,
        "subject": subject,
        "conversationId": "conv-1",
        "from": {"emailAddress": {"name": "Dist", "address": "dist@example.com"}},
        "receivedDateTime": "2026-07-29T10:00:00Z",
        "hasAttachments": True,
        "isRead": False,
        "bodyPreview": "report",
    }


def test_scenario1_mark_as_read_success_keeps_report(db: Session, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "ok.xlsx",
        distributor="Mark Read OK Dist",
        reporting_month="July 2026",
        rows=[(1, "Cust A", "Paper", "P1", 10, 1, 2)],
    )
    content = path.read_bytes()

    graph = MagicMock()
    graph.resolve_mailbox = MagicMock(return_value="mb@test.com")
    graph.list_unread_messages = MagicMock(
        return_value=[_graph_message("g-ok-1", internet_id="<ok-1@test>")]
    )
    graph.list_attachments = MagicMock(
        return_value=[
            {
                "id": "att-1",
                "name": "ok.xlsx",
                "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": len(content),
            }
        ]
    )
    graph.download_attachment = MagicMock(return_value=content)
    graph.mark_as_read = MagicMock()
    from app.integrations.graph.client import GraphClient

    graph.is_excel_attachment = GraphClient.is_excel_attachment

    svc = OutlookSyncService(db, graph_client=graph)
    job = svc.sync(OutlookSyncRequest(mark_as_read=True), actor="test")

    assert job.status == SyncStatus.COMPLETED.value
    assert job.failures == 0
    assert job.reports_created >= 1
    email = EmailMessageRepository(db).get_by_graph_id("g-ok-1")
    assert email is not None
    assert email.is_read is True
    assert email.process_status == EmailProcessStatus.MARKED_READ.value
    graph.mark_as_read.assert_called()


def test_scenario2_mark_as_read_403_keeps_report(db: Session, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "keep.xlsx",
        distributor="Mark Read Fail Dist",
        reporting_month="July 2026",
        rows=[(1, "Cust B", "Paper", "P2", 20, 3, 4)],
    )
    content = path.read_bytes()

    graph = MagicMock()
    graph.resolve_mailbox = MagicMock(return_value="mb@test.com")
    graph.list_unread_messages = MagicMock(
        return_value=[_graph_message("g-fail-1", internet_id="<fail-1@test>", subject="Keep Me")]
    )
    graph.list_attachments = MagicMock(
        return_value=[
            {
                "id": "att-fail",
                "name": "keep.xlsx",
                "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": len(content),
            }
        ]
    )
    graph.download_attachment = MagicMock(return_value=content)
    graph.mark_as_read = MagicMock(
        side_effect=GraphAPIError("Microsoft Graph API returned HTTP 403")
    )
    from app.integrations.graph.client import GraphClient

    graph.is_excel_attachment = GraphClient.is_excel_attachment

    svc = OutlookSyncService(db, graph_client=graph)
    job = svc.sync(OutlookSyncRequest(mark_as_read=True), actor="test")

    assert job.status == SyncStatus.COMPLETED.value
    assert job.failures == 0
    assert job.reports_created >= 1
    assert job.details and job.details.get("warnings")
    assert job.details["warnings"][0]["warning"] == "mark_as_read_failed"

    email = EmailMessageRepository(db).get_by_graph_id("g-fail-1")
    assert email is not None
    assert email.is_read is False
    assert email.process_status == EmailProcessStatus.INSERTED.value

    reports = [
        r
        for r in db.query(Report).filter(Report.email_message_id == email.id, Report.is_deleted.is_(False)).all()
    ]
    assert len(reports) >= 1


def test_scenario3_resync_dedupes_no_duplicate_report(db: Session, tmp_path: Path):
    path = build_official_workbook(
        tmp_path / "dedupe.xlsx",
        distributor="Dedupe Dist Co",
        reporting_month="August 2026",
        rows=[(1, "Cust C", "Paper", "P3", 30, 5, 6)],
    )
    content = path.read_bytes()
    msg = _graph_message("g-dedupe-1", internet_id="<dedupe-1@test>", subject="Dedupe")

    graph = MagicMock()
    graph.resolve_mailbox = MagicMock(return_value="mb@test.com")
    graph.list_unread_messages = MagicMock(return_value=[msg])
    graph.list_attachments = MagicMock(
        return_value=[
            {
                "id": "att-d",
                "name": "dedupe.xlsx",
                "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": len(content),
            }
        ]
    )
    graph.download_attachment = MagicMock(return_value=content)
    graph.mark_as_read = MagicMock(
        side_effect=GraphAPIError("Microsoft Graph API returned HTTP 403")
    )
    from app.integrations.graph.client import GraphClient

    graph.is_excel_attachment = GraphClient.is_excel_attachment

    svc = OutlookSyncService(db, graph_client=graph)
    job1 = svc.sync(OutlookSyncRequest(mark_as_read=True), actor="test")
    assert job1.reports_created >= 1

    email = EmailMessageRepository(db).get_by_graph_id("g-dedupe-1")
    assert email is not None
    reports_after_first = [
        r
        for r in db.query(Report).filter(Report.email_message_id == email.id).all()
        if not r.is_deleted
    ]
    count_after_first = len(reports_after_first)

    # Second sync: still unread in Graph; dedupe must not create a second active report
    job2 = svc.sync(OutlookSyncRequest(mark_as_read=True), actor="test")
    assert job2.status == SyncStatus.COMPLETED.value
    assert job2.reports_created == 0
    processed = (job2.details or {}).get("processed") or []
    assert processed and processed[0]["status"] == "already_processed"

    reports_after_second = [
        r
        for r in db.query(Report).filter(Report.email_message_id == email.id).all()
        if not r.is_deleted
    ]
    assert len(reports_after_second) == count_after_first
