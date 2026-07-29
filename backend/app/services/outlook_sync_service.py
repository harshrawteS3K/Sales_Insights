"""Outlook / Microsoft Graph synchronization service."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction, EmailProcessStatus, ReportSource, SyncStatus
from app.exceptions import GraphAPIError
from app.integrations.graph.client import GraphClient
from app.models.email_message import EmailAttachment, EmailMessage
from app.models.sync_job import SyncJob
from app.repositories.email_repository import EmailAttachmentRepository, EmailMessageRepository
from app.repositories.master_repository import SyncJobRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.email import FrontendEmailRecord, OutlookSyncRequest
from app.services.audit_service import AuditService
from app.services.report_service import ReportService
from app.utils.datetime_utils import format_frontend_datetime, utc_now
from app.utils.files import get_upload_subdir, save_bytes
from app.utils.hashing import sha256_bytes

logger = get_logger(__name__)

_TERMINAL_PROCESSED = {
    EmailProcessStatus.INSERTED.value,
    EmailProcessStatus.MARKED_READ.value,
}


def _parse_graph_datetime(value: Optional[str]) -> datetime:
    """Parse Graph ISO datetime into aware datetime."""
    if not value:
        return utc_now()
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


class OutlookSyncService:
    """Orchestrates unread-mail sync, Excel download, parse, insert, and mark-as-read."""

    def __init__(self, db: Session, graph_client: Optional[GraphClient] = None) -> None:
        self.db = db
        self.graph = graph_client or GraphClient()
        self.emails = EmailMessageRepository(db)
        self.attachments = EmailAttachmentRepository(db)
        self.sync_jobs = SyncJobRepository(db)
        self.reports = ReportService(db)
        self.audit = AuditService(db)

    def list_emails(self, *, skip: int = 0, limit: int = 200) -> List[EmailMessage]:
        """List stored email metadata."""
        return self.emails.list_extracted(skip=skip, limit=limit)

    def to_frontend_emails(self, messages: List[EmailMessage]) -> List[FrontendEmailRecord]:
        """Map ORM emails to frontend EmailRecord shape."""
        return [
            FrontendEmailRecord(
                id=msg.id,
                senderName=msg.sender_name or msg.sender_email,
                senderEmail=msg.sender_email,
                subject=msg.subject,
                dateReceived=format_frontend_datetime(msg.received_at),
                confidenceScore=msg.confidence_score if msg.confidence_score is not None else 0,
            )
            for msg in messages
        ]

    def delete_email_record(self, email_id: int, *, actor: str) -> Dict[str, Any]:
        """
        Soft-delete an email processing history record from Sales Insights.

        Soft-deletes attachments so Graph attachment IDs can be reused on reprocess.
        Does NOT delete the message from Outlook / Microsoft Graph.
        """
        email = self.emails.get_or_raise(email_id)
        attachments_deleted = self.attachments.soft_delete_for_email(email.id)
        self.emails.soft_delete(email)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DELETED,
                details=(
                    f"Deleted email processing history id={email_id} | "
                    f"subject={email.subject!r} | sender={email.sender_email} | "
                    f"attachments_soft_deleted={attachments_deleted} | "
                    f"outlook_message_retained=true"
                ),
                entity_type="email_message",
                entity_id=str(email_id),
            )
        )
        logger.info(
            "Email history deleted | id={} | actor={} | graph_id={} | attachments={} | outlook_retained=true",
            email_id,
            actor,
            email.graph_message_id,
            attachments_deleted,
        )
        return {
            "success": True,
            "message": "Email processing record removed from Sales Insights",
            "deletedId": email_id,
            "outlookDeleted": False,
        }

    def get_sync_job(self, job_id: int) -> SyncJob:
        """Get sync job by id."""
        return self.sync_jobs.get_or_raise(job_id)

    def list_sync_jobs(self, *, skip: int = 0, limit: int = 50) -> List[SyncJob]:
        """List sync jobs newest first."""
        return self.sync_jobs.list(skip=skip, limit=limit, order_by=SyncJob.started_at.desc())

    def count_sync_jobs(self) -> int:
        """Return total sync job count."""
        return self.sync_jobs.count()

    def sync(self, request: OutlookSyncRequest, *, actor: str = "system") -> SyncJob:
        """
        Run a full Outlook sync.

        Each message runs inside a SAVEPOINT so a failed ingest never leaves
        retired reports / partial sales committed while the outer sync continues.
        """
        mailbox = self.graph.resolve_mailbox(request.mailbox)
        job = SyncJob(
            status=SyncStatus.STARTED.value,
            mailbox=mailbox,
            started_at=utc_now(),
            triggered_by=actor,
            details={"mark_as_read": request.mark_as_read, "max_messages": request.max_messages},
        )
        job = self.sync_jobs.create(job)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.SYNCED,
                details=f"Started Outlook sync for mailbox {mailbox}",
                entity_type="sync_job",
                entity_id=str(job.id),
            )
        )

        details: Dict[str, Any] = {"processed": [], "failures": []}
        try:
            messages = self.graph.list_unread_messages(
                mailbox=mailbox,
                top=request.max_messages,
                has_attachments=True,
            )
            job.emails_found = len(messages)
            details["emails_found"] = len(messages)
            details["max_messages"] = request.max_messages
            self.db.flush()
            logger.info(
                "Outlook sync listed unread | job={} | mailbox={} | found={} | max_messages={}",
                job.id,
                mailbox,
                len(messages),
                request.max_messages,
            )

            for message in messages:
                message_id = message.get("id")
                try:
                    # SAVEPOINT: rollback this message only on failure (no partial replace)
                    with self.db.begin_nested():
                        result = self._process_message(
                            message,
                            mailbox=mailbox,
                            mark_as_read=request.mark_as_read,
                            actor=actor,
                        )
                    details["processed"].append(result)
                    job.emails_processed += 1
                    job.attachments_downloaded += int(result.get("attachments_downloaded", 0))
                    job.reports_created += int(result.get("reports_created", 0))
                    job.records_inserted += int(result.get("records_inserted", 0))
                    job.duplicates_skipped += int(result.get("duplicates_skipped", 0))
                except Exception as exc:
                    job.failures += 1
                    details["failures"].append(
                        {"message_id": message_id, "error": str(exc)}
                    )
                    logger.exception(
                        "Failed processing Graph message (rolled back) | id={} | error={}",
                        message_id,
                        exc,
                    )

            if job.failures and job.emails_processed:
                job.status = SyncStatus.PARTIAL.value
            elif job.failures and not job.emails_processed:
                job.status = SyncStatus.FAILED.value
            else:
                job.status = SyncStatus.COMPLETED.value

            job.completed_at = utc_now()
            job.details = details
            self.db.flush()
            self.db.refresh(job)
            logger.info(
                "Sync Completed | job={} | status={} | processed={} | failures={} | records={}",
                job.id,
                job.status,
                job.emails_processed,
                job.failures,
                job.records_inserted,
            )
            return job
        except Exception as exc:
            job.status = SyncStatus.FAILED.value
            job.error_message = str(exc)
            job.completed_at = utc_now()
            job.details = details
            self.db.flush()
            self.db.refresh(job)
            logger.exception("Outlook sync failed | job={} | stage=sync | error={}", job.id, exc)
            if isinstance(exc, GraphAPIError):
                raise
            raise GraphAPIError(f"Outlook sync failed: {exc}") from exc

    def _ensure_marked_read(
        self,
        email: EmailMessage,
        *,
        graph_id: str,
        mailbox: str,
        reason: str,
    ) -> bool:
        """
        PATCH Graph isRead=true and mirror DB state.

        Returns True on success. Raises GraphAPIError on failure (caller decides rollback).
        """
        logger.info(
            "Mark As Read starting | message_id={} | email_id={} | reason={}",
            graph_id,
            email.id,
            reason,
        )
        self.graph.mark_as_read(graph_id, mailbox=mailbox)
        email.is_read = True
        if email.process_status in {
            EmailProcessStatus.INSERTED.value,
            EmailProcessStatus.MARKED_READ.value,
            EmailProcessStatus.SKIPPED.value,
        }:
            if email.process_status != EmailProcessStatus.SKIPPED.value:
                email.process_status = EmailProcessStatus.MARKED_READ.value
        self.db.flush()
        logger.info(
            "Mark As Read success | message_id={} | email_id={} | status={}",
            graph_id,
            email.id,
            email.process_status,
        )
        return True

    def _find_existing_email(self, message: Dict[str, Any]) -> Optional[EmailMessage]:
        """Resolve prior email by graph_message_id, then internet_message_id."""
        graph_id = message.get("id") or ""
        existing = self.emails.get_by_graph_id(graph_id) if graph_id else None
        if existing:
            return existing
        internet_id = (message.get("internetMessageId") or "").strip()
        if internet_id:
            existing = self.emails.get_by_internet_message_id(internet_id)
            if existing:
                logger.info(
                    "Email dedupe hit via internet_message_id | graph_id={} | internet_id={} | email_id={}",
                    graph_id,
                    internet_id,
                    existing.id,
                )
                # Keep latest Graph id so mark-as-read targets the current message
                if graph_id and existing.graph_message_id != graph_id:
                    existing.graph_message_id = graph_id
                    self.db.flush()
        return existing

    def _process_message(
        self,
        message: Dict[str, Any],
        *,
        mailbox: str,
        mark_as_read: bool,
        actor: str,
    ) -> Dict[str, Any]:
        """Process a single Graph message end-to-end (idempotent)."""
        graph_id = message["id"]
        existing = self._find_existing_email(message)

        # Already fully processed — do not re-ingest; only ensure Graph is read
        if existing and existing.process_status in _TERMINAL_PROCESSED:
            logger.info(
                "Email already processed | message_id={} | email_id={} | status={} | retry_mark_read={}",
                graph_id,
                existing.id,
                existing.process_status,
                mark_as_read,
            )
            if mark_as_read:
                self._ensure_marked_read(
                    existing,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="already_processed_retry",
                )
            return {
                "message_id": graph_id,
                "status": "already_processed",
                "attachments_downloaded": 0,
                "reports_created": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
            }

        # Previously skipped (no Excel) — still unread in Graph; mark read & stop
        if existing and existing.process_status == EmailProcessStatus.SKIPPED.value:
            logger.info(
                "Email previously skipped (no Excel) | message_id={} | email_id={}",
                graph_id,
                existing.id,
            )
            if mark_as_read:
                self._ensure_marked_read(
                    existing,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="skipped_retry_mark_read",
                )
            return {
                "message_id": graph_id,
                "status": "skipped_no_excel",
                "attachments_downloaded": 0,
                "reports_created": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
            }

        sender_name, sender_email = GraphClient.extract_sender(message)
        email = existing or EmailMessage(
            graph_message_id=graph_id,
            conversation_id=message.get("conversationId"),
            internet_message_id=message.get("internetMessageId"),
            subject=message.get("subject") or "(no subject)",
            sender_name=sender_name,
            sender_email=sender_email or "unknown@unknown",
            received_at=_parse_graph_datetime(message.get("receivedDateTime")),
            body_preview=message.get("bodyPreview"),
            has_attachments=bool(message.get("hasAttachments")),
            is_read=bool(message.get("isRead")),
            process_status=EmailProcessStatus.UNREAD.value,
            confidence_score=None,
            mailbox=mailbox,
        )
        if existing is None:
            email = self.emails.create(email)
        elif not email.internet_message_id and message.get("internetMessageId"):
            email.internet_message_id = message.get("internetMessageId")
            self.db.flush()

        attachments = self.graph.list_attachments(graph_id, mailbox=mailbox)
        excel_attachments = [a for a in attachments if GraphClient.is_excel_attachment(a)]
        logger.info(
            "Excel Attachment Found | message_id={} | total_attachments={} | excel={}",
            graph_id,
            len(attachments),
            len(excel_attachments),
        )
        if not excel_attachments:
            email.process_status = EmailProcessStatus.SKIPPED.value
            email.error_message = "No Excel attachments found"
            self.db.flush()
            if mark_as_read:
                self._ensure_marked_read(
                    email,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="skipped_no_excel",
                )
            return {
                "message_id": graph_id,
                "status": "skipped_no_excel",
                "attachments_downloaded": 0,
                "reports_created": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
            }

        attachments_downloaded = 0
        reports_created = 0
        records_inserted = 0
        duplicates_skipped = 0
        any_success = False
        quality_scores: List[int] = []

        for attachment in excel_attachments:
            att_id = attachment["id"]
            file_name = attachment.get("name") or "attachment.xlsx"
            size_bytes = attachment.get("size")
            logger.info(
                "Attachment Downloaded starting | file={} | size={} | ext={}",
                file_name,
                size_bytes,
                Path(file_name).suffix.lower(),
            )
            content = self.graph.download_attachment(graph_id, att_id, mailbox=mailbox)
            content_hash = sha256_bytes(content)
            path = save_bytes(content, get_upload_subdir("attachments"), file_name)
            attachments_downloaded += 1
            logger.info(
                "Attachment Downloaded | file={} | bytes={} | path={}",
                file_name,
                len(content),
                path,
            )

            att_entity = self.attachments.get_by_graph_id(att_id)
            if att_entity is None:
                att_entity = EmailAttachment(
                    graph_attachment_id=att_id,
                    file_name=file_name,
                    content_type=attachment.get("contentType"),
                    size_bytes=attachment.get("size") or len(content),
                    file_path=str(path),
                    content_hash=content_hash,
                    is_excel=True,
                    email_message_id=email.id,
                )
                self.attachments.create(att_entity)
            else:
                self.attachments.update(
                    att_entity,
                    {
                        "file_path": str(path),
                        "content_hash": content_hash,
                        "size_bytes": attachment.get("size") or len(content),
                    },
                )

            email.process_status = EmailProcessStatus.DOWNLOADED.value

            try:
                report, inserted, was_duplicate, quality_score = self.reports.ingest_excel(
                    path,
                    source=ReportSource.OUTLOOK,
                    report_name=f"{email.subject} - {file_name}",
                    email_message_id=email.id,
                    actor=actor,
                    mark_duplicate_as_error=False,
                )
                quality_scores.append(quality_score)
                if was_duplicate:
                    duplicates_skipped += 1
                else:
                    reports_created += 1
                    records_inserted += inserted
                    any_success = True
                logger.info(
                    "Attachment ingested | message_id={} | file={} | quality={} | duplicate={}",
                    graph_id,
                    file_name,
                    quality_score,
                    was_duplicate,
                )
            except Exception as exc:
                email.process_status = EmailProcessStatus.FAILED.value
                email.error_message = str(exc)
                logger.exception(
                    "Failed ingesting attachment | message={} attachment={} | rolling back message",
                    graph_id,
                    file_name,
                )
                raise

        if quality_scores:
            email.confidence_score = min(quality_scores)

        if any_success or duplicates_skipped:
            email.process_status = EmailProcessStatus.INSERTED.value
            email.error_message = None
            self.db.flush()
            # Mark read BEFORE leaving savepoint — failure rolls back ingest
            if mark_as_read:
                self._ensure_marked_read(
                    email,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="ingest_success",
                )
            else:
                self.db.flush()

        return {
            "message_id": graph_id,
            "status": email.process_status,
            "attachments_downloaded": attachments_downloaded,
            "reports_created": reports_created,
            "records_inserted": records_inserted,
            "duplicates_skipped": duplicates_skipped,
            "confidence_score": email.confidence_score,
        }
