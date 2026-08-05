"""Outlook / Microsoft Graph synchronization service."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction, AuditStatus, EmailProcessStatus, ReportSource, SyncStatus
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
        from app.utils.outlook_links import resolve_outlook_open_url

        return [
            FrontendEmailRecord(
                id=msg.id,
                senderName=msg.sender_name or msg.sender_email,
                senderEmail=msg.sender_email,
                subject=msg.subject,
                dateReceived=format_frontend_datetime(msg.received_at),
                confidenceScore=msg.confidence_score if msg.confidence_score is not None else 0,
                outlookWebLink=resolve_outlook_open_url(
                    web_link=getattr(msg, "outlook_web_link", None),
                    graph_message_id=msg.graph_message_id,
                ),
                graphMessageId=msg.graph_message_id,
                mailbox=msg.mailbox,
            )
            for msg in messages
        ]

    def resolve_outlook_open_link(self, email_id: int) -> Dict[str, Any]:
        """
        Resolve a navigable Outlook URL for an email processing history row.

        Verifies the Graph message still exists when credentials allow.
        """
        from app.exceptions import NotFoundError
        from app.utils.outlook_links import resolve_outlook_open_url

        email = self.emails.get_or_raise(email_id)
        url = resolve_outlook_open_url(
            web_link=getattr(email, "outlook_web_link", None),
            graph_message_id=email.graph_message_id,
        )
        if not url:
            raise NotFoundError(
                "Original Outlook email is no longer available.",
                details={"email_id": email_id},
            )

        # Prefer live Graph webLink; refresh stored link when possible
        try:
            live = self.graph.get_message(email.graph_message_id, mailbox=email.mailbox)
            live_link = (live or {}).get("webLink") or url
            if live_link and live_link != getattr(email, "outlook_web_link", None):
                email.outlook_web_link = live_link
                self.db.flush()
            return {
                "success": True,
                "url": live_link,
                "available": True,
                "message": None,
            }
        except GraphAPIError as exc:
            details = str(exc.details or "") if hasattr(exc, "details") else str(exc)
            status_hint = str(exc)
            if "404" in status_hint or "ErrorItemNotFound" in details or "not found" in details.lower():
                raise NotFoundError(
                    "Original Outlook email is no longer available.",
                    details={"email_id": email_id, "graph_message_id": email.graph_message_id},
                ) from exc
            # Auth/permission issues: still return stored link so user can try
            logger.warning(
                "Outlook link verify failed; returning stored URL | email_id={} | error={}",
                email_id,
                exc,
            )
            return {
                "success": True,
                "url": url,
                "available": True,
                "message": "Could not verify message in Graph; opening stored Outlook link.",
            }

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

        Each message ingest runs inside a SAVEPOINT so a failed ingest never leaves
        retired reports / partial sales committed while the outer sync continues.
        Mark-as-read runs only after the ingest savepoint succeeds and never rolls
        back business data.
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

        details: Dict[str, Any] = {"processed": [], "failures": [], "warnings": []}
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
                    # SAVEPOINT: ingest only — mark-as-read must NOT participate in rollback.
                    with self.db.begin_nested():
                        result = self._process_message(
                            message,
                            mailbox=mailbox,
                            mark_as_read=False,
                            actor=actor,
                        )
                    # Ingest savepoint released successfully — business data is durable here.
                    if request.mark_as_read:
                        email = self._email_for_mark_read(message, result)
                        if email is not None:
                            mark_ok = self._ensure_marked_read(
                                email,
                                graph_id=str(message_id or ""),
                                mailbox=mailbox,
                                reason="post_ingest_commit",
                            )
                            result["mark_as_read_ok"] = mark_ok
                            if not mark_ok:
                                err = (
                                    email.error_message
                                    or "Graph mark-as-read failed; report was kept"
                                )
                                warning = {
                                    "message_id": message_id,
                                    "warning": "mark_as_read_failed",
                                    "email_id": email.id,
                                    "error": err,
                                }
                                details["warnings"].append(warning)
                                result["mark_as_read_error"] = err
                        else:
                            result["mark_as_read_ok"] = False
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
            status_badge = (
                AuditStatus.FAILED.value
                if job.status == SyncStatus.FAILED.value
                else (
                    AuditStatus.WARNING.value
                    if job.status == SyncStatus.PARTIAL.value
                    else AuditStatus.SUCCESS.value
                )
            )
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.EXTRACTED
                    if job.status != SyncStatus.FAILED.value
                    else AuditAction.FAILED,
                    details=(
                        f"Outlook sync {job.status}: processed {job.emails_processed} emails, "
                        f"imported {job.reports_created} reports, "
                        f"replaced/skipped {job.duplicates_skipped}, "
                        f"failures {job.failures}"
                    ),
                    entity_type="sync_job",
                    entity_id=str(job.id),
                    module="Emails",
                    status=status_badge,
                    extra_metadata={
                        "emails_found": job.emails_found,
                        "emails_processed": job.emails_processed,
                        "reports_created": job.reports_created,
                        "records_inserted": job.records_inserted,
                        "duplicates_skipped": job.duplicates_skipped,
                        "failures": job.failures,
                    },
                )
            )
            logger.info(
                "Sync Completed | job={} | status={} | processed={} | failures={} | "
                "warnings={} | records={}",
                job.id,
                job.status,
                job.emails_processed,
                job.failures,
                len(details.get("warnings") or []),
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
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.FAILED,
                    details=f"Outlook sync failed: {exc}",
                    entity_type="sync_job",
                    entity_id=str(job.id),
                    module="Emails",
                    status=AuditStatus.FAILED.value,
                )
            )
            logger.exception("Outlook sync failed | job={} | stage=sync | error={}", job.id, exc)
            if isinstance(exc, GraphAPIError):
                raise
            raise GraphAPIError(f"Outlook sync failed: {exc}") from exc

    def _email_for_mark_read(
        self,
        message: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Optional[EmailMessage]:
        """Resolve the email row to mark read after a successful ingest savepoint."""
        email_id = result.get("email_id")
        if email_id is not None:
            email = self.emails.get_by_id(int(email_id))
            if email is not None:
                return email
        return self._find_existing_email(message)

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

        Returns True on success, False on Graph/network failure.
        Never raises — mark-as-read must not roll back committed business data.
        """
        logger.info(
            "Mark As Read starting | message_id={} | email_id={} | reason={}",
            graph_id,
            email.id,
            reason,
        )
        try:
            self.graph.mark_as_read(graph_id, mailbox=mailbox)
        except Exception as exc:
            # Stash last error on the result path via email (non-fatal operational note)
            email.error_message = (
                f"Mark-as-read failed (data kept): {exc}"
                if not email.error_message
                else email.error_message
            )
            self.db.flush()
            logger.warning(
                "Mark As Read failed (report kept) | message_id={} | email_id={} | "
                "reason={} | error={}",
                graph_id,
                email.id,
                reason,
                exc,
            )
            return False

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
            web_link = (message.get("webLink") or "").strip()
            if web_link and existing.outlook_web_link != web_link:
                existing.outlook_web_link = web_link
                self.db.flush()
            mark_ok: Optional[bool] = None
            if mark_as_read:
                mark_ok = self._ensure_marked_read(
                    existing,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="already_processed_retry",
                )
            return {
                "message_id": graph_id,
                "email_id": existing.id,
                "status": "already_processed",
                "attachments_downloaded": 0,
                "reports_created": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
                "mark_as_read_ok": mark_ok,
            }

        # Previously skipped (no Excel) — still unread in Graph; mark read & stop
        if existing and existing.process_status == EmailProcessStatus.SKIPPED.value:
            logger.info(
                "Email previously skipped (no Excel) | message_id={} | email_id={}",
                graph_id,
                existing.id,
            )
            mark_ok = None
            if mark_as_read:
                mark_ok = self._ensure_marked_read(
                    existing,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="skipped_retry_mark_read",
                )
            return {
                "message_id": graph_id,
                "email_id": existing.id,
                "status": "skipped_no_excel",
                "attachments_downloaded": 0,
                "reports_created": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
                "mark_as_read_ok": mark_ok,
            }

        sender_name, sender_email = GraphClient.extract_sender(message)
        web_link = (message.get("webLink") or "").strip() or None
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
            outlook_web_link=web_link,
        )
        if existing is None:
            email = self.emails.create(email)
        else:
            if web_link and existing.outlook_web_link != web_link:
                email.outlook_web_link = web_link
            if not email.internet_message_id and message.get("internetMessageId"):
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
            mark_ok = None
            if mark_as_read:
                mark_ok = self._ensure_marked_read(
                    email,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="skipped_no_excel",
                )
            return {
                "message_id": graph_id,
                "email_id": email.id,
                "status": "skipped_no_excel",
                "attachments_downloaded": 0,
                "reports_created": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
                "mark_as_read_ok": mark_ok,
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

        mark_ok = None
        if any_success or duplicates_skipped:
            email.process_status = EmailProcessStatus.INSERTED.value
            email.error_message = None
            self.db.flush()
            # Mark-as-read is optional here (direct callers). Sync() marks after savepoint.
            if mark_as_read:
                mark_ok = self._ensure_marked_read(
                    email,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="ingest_success",
                )

        return {
            "message_id": graph_id,
            "email_id": email.id,
            "status": email.process_status,
            "attachments_downloaded": attachments_downloaded,
            "reports_created": reports_created,
            "records_inserted": records_inserted,
            "duplicates_skipped": duplicates_skipped,
            "confidence_score": email.confidence_score,
            "mark_as_read_ok": mark_ok,
        }
