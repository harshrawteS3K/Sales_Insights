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

# Graph mark-as-read must NOT run for these — leave mail unread so the user can fix & re-sync.
_NO_GRAPH_MARK_READ_STATUSES = {
    EmailProcessStatus.INVALID_SUBJECT.value,
    "segment_unauthorized",
    EmailProcessStatus.FAILED.value,
}


def _should_mark_graph_read(result: Dict[str, Any]) -> bool:
    """Only clear Outlook unread after a successful/intentional terminal outcome."""
    status = str(result.get("status") or "")
    if status in _NO_GRAPH_MARK_READ_STATUSES:
        return False
    if int(result.get("attachments_downloaded") or 0) > 0:
        return True
    if status in {
        "already_processed",
        "skipped_no_excel",
        EmailProcessStatus.DOWNLOADED.value,
        EmailProcessStatus.PARSED.value,
        EmailProcessStatus.INSERTED.value,
        EmailProcessStatus.MARKED_READ.value,
    }:
        return True
    return False


def _parse_graph_datetime(value: Optional[str]) -> datetime:
    """Parse Graph ISO datetime into aware datetime."""
    if not value:
        return utc_now()
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _sync_result_message(
    *,
    user_email: Optional[str],
    emails_found: int,
    emails_processed: int,
    reports_created: int,
    failures: int,
    status: str,
    details: Dict[str, Any],
) -> str:
    """Human-readable sync outcome for the UI (no false 'will be extracted' promises)."""
    if status == SyncStatus.FAILED.value and emails_processed == 0 and failures:
        return "Outlook sync failed while processing emails. Check job details."

    if emails_found == 0 and user_email:
        probe = details.get("inbox_unread_excel_probe")
        others = details.get("other_senders_sample") or []
        if probe is None:
            return (
                f"Sync complete. No unread Excel emails FROM {user_email} "
                f"in the Sales Insights inbox — nothing to extract."
            )
        if int(probe) == 0:
            return (
                f"Sync complete. No unread Excel emails in the Sales Insights inbox "
                f"(including none from {user_email}). Nothing to extract right now."
            )
        sample = ", ".join(others[:3]) if others else "other addresses"
        return (
            f"Sync complete. No unread Excel emails FROM {user_email}. "
            f"The inbox has {probe} unread Excel email(s) from other senders "
            f"({sample}) — those are not extracted for your account."
        )

    if emails_found == 0:
        return "Sync complete. No unread Excel emails in the Sales Insights inbox."

    recovered = int(details.get("recovered_count") or 0)
    parts = [
        f"Sync complete. Found {emails_found} email(s)",
        f"processed {emails_processed}",
    ]
    if recovered:
        parts.append(f"recovered {recovered} previously missed")
    if reports_created:
        parts.append(f"created {reports_created} report(s)")
    if failures:
        parts.append(f"{failures} failure(s)")
    return "; ".join(parts) + "."


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

    def list_emails(
        self,
        *,
        skip: int = 0,
        limit: int = 200,
        allowed_segments: Optional[List[str]] = None,
        allowed_companies: Optional[List[str]] = None,
        sender_email: Optional[str] = None,
    ) -> List[EmailMessage]:
        """List Emails-tab work queue (excludes already consolidated)."""
        return self.emails.list_extracted(
            skip=skip,
            limit=limit,
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
            sender_email=sender_email,
        )

    def to_frontend_emails(self, messages: List[EmailMessage]) -> List[FrontendEmailRecord]:
        """Map ORM emails to frontend EmailRecord shape."""
        from app.utils.outlook_links import resolve_outlook_open_url

        status_label_map = {
            EmailProcessStatus.UNREAD.value: "New",
            EmailProcessStatus.DOWNLOADED.value: "New",
            EmailProcessStatus.PARSED.value: "Parsed",
            EmailProcessStatus.INSERTED.value: "Imported",
            EmailProcessStatus.MARKED_READ.value: "Imported",
            EmailProcessStatus.FAILED.value: "Failed",
            EmailProcessStatus.SKIPPED.value: "Failed",
            EmailProcessStatus.INVALID_SUBJECT.value: "Invalid Subject",
        }

        result: List[FrontendEmailRecord] = []
        for msg in messages:
            excel_name = None
            has_excel = False
            excel_path: Optional[str] = None
            excel_count = 0
            for att in msg.attachments or []:
                if getattr(att, "is_deleted", False):
                    continue
                if att.is_excel or (att.file_name or "").lower().endswith((".xlsx", ".xlsm", ".xls")):
                    excel_count += 1
                    if excel_name is None:
                        excel_name = att.file_name
                        has_excel = True
                        excel_path = att.file_path
            if excel_count > 1 and excel_name:
                excel_name = f"{excel_name} (+{excel_count - 1} more)"

            # Always refresh Accuracy from the Excel for non-imported emails so the
            # list never shows a stale score (e.g. 76% from an older parser pass).
            if (
                has_excel
                and excel_path
                and msg.process_status
                not in {
                    EmailProcessStatus.INSERTED.value,
                    EmailProcessStatus.MARKED_READ.value,
                    EmailProcessStatus.FAILED.value,
                    EmailProcessStatus.SKIPPED.value,
                }
            ):
                try:
                    from app.services.erp_score_queue import enqueue_email_score, is_pending

                    path = Path(excel_path)
                    if path.is_file():
                        # Never re-parse synchronously on list load (latency + OpenAI).
                        # Queue background score when accuracy is still pending.
                        score = msg.confidence_score
                        if score is None or int(score) <= 0:
                            if not is_pending(int(msg.id)):
                                enqueue_email_score(int(msg.id), allow_llm=True)
                        elif msg.process_status in {
                            EmailProcessStatus.UNREAD.value,
                            EmailProcessStatus.DOWNLOADED.value,
                        }:
                            msg.process_status = EmailProcessStatus.PARSED.value
                            self.db.flush()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ERP accuracy refresh failed | email_id={} | err={}",
                        msg.id,
                        exc,
                    )

            dist_name = msg.parsed_distributor
            if not dist_name:
                try:
                    from app.repositories.distributor_repository import DistributorRepository

                    dist = DistributorRepository(self.db).get_by_email(msg.sender_email)
                    if dist is not None:
                        dist_name = dist.company or dist.name
                except Exception:  # noqa: BLE001
                    dist_name = None

            status = msg.process_status or EmailProcessStatus.UNREAD.value
            result.append(
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
                    processStatus=status,
                    statusLabel=status_label_map.get(status, "New"),
                    attachmentName=excel_name,
                    distributorName=dist_name,
                    distributor=msg.parsed_distributor,
                    location=msg.parsed_location,
                    segment=msg.parsed_segment,
                    quarter=msg.detected_quarter,
                    subjectValid=bool(msg.subject_valid),
                    hasExcel=has_excel,
                    errorMessage=msg.error_message,
                    mappingSource=getattr(msg, "mapping_source", None),
                )
            )
        return result

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

    def sync_for_user(
        self,
        *,
        job_id: Optional[int] = None,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        user_role: str = "user",
        request: Optional[OutlookSyncRequest] = None,
        actor: str = "system",
        sync_trigger: str = "manual",
    ) -> SyncJob:
        """
        Run Outlook sync for a specific logged-in user.

        Filters Graph unread messages by sender email (`FROM == logged_in_user_email`)
        and validates that parsed subject distributor is assigned to the user.
        """
        sync_req = request or OutlookSyncRequest()
        mailbox = self.graph.resolve_mailbox(sync_req.mailbox)
        is_automated = (sync_trigger or "").strip().lower() == "automated"
        audit_action = (
            AuditAction.AUTOMATED_OUTLOOK_SYNC
            if is_automated
            else AuditAction.MANUAL_OUTLOOK_SYNC
        )
        triggered_by_label = "System" if is_automated else actor

        job = self.sync_jobs.get_by_id(job_id) if job_id else None
        if not job:
            job = SyncJob(
                status=SyncStatus.STARTED.value,
                mailbox=mailbox,
                started_at=utc_now(),
                triggered_by=triggered_by_label,
                details={
                    "mark_as_read": sync_req.mark_as_read,
                    "max_messages": sync_req.max_messages,
                    "user_email": user_email,
                    "sync_trigger": sync_trigger,
                },
            )
            job = self.sync_jobs.create(job)
        else:
            job.status = SyncStatus.STARTED.value
            job.started_at = utc_now()
            if not job.triggered_by:
                job.triggered_by = triggered_by_label
            self.db.flush()

        started_at = job.started_at or utc_now()

        details: Dict[str, Any] = {
            "processed": [],
            "failures": [],
            "warnings": [],
            "user_email": user_email,
            "sync_trigger": sync_trigger,
            "triggered_by": triggered_by_label,
        }
        try:
            messages = self.graph.list_unread_messages(
                mailbox=mailbox,
                top=sync_req.max_messages,
                has_attachments=True,
                sender_email=user_email,
            )
            job.emails_found = len(messages)
            details["emails_found"] = len(messages)
            details["max_messages"] = sync_req.max_messages
            details["sender_filter"] = user_email

            # When sender-scoped sync finds nothing, probe the inbox so the UI can
            # distinguish "mailbox idle" vs "mail exists but not from this user".
            if user_email and not messages:
                try:
                    probe = self.graph.list_unread_messages(
                        mailbox=mailbox,
                        top=20,
                        has_attachments=True,
                        sender_email=None,
                    )
                    other_senders: List[str] = []
                    for msg in probe:
                        _, s_email = self.graph.extract_sender(msg)
                        addr = (s_email or "").strip().lower()
                        if addr and addr not in other_senders:
                            other_senders.append(addr)
                    details["inbox_unread_excel_probe"] = len(probe)
                    details["other_senders_sample"] = other_senders[:8]
                except Exception as probe_exc:  # noqa: BLE001
                    logger.warning(
                        "Inbox probe after empty sender sync failed | job={} | err={}",
                        job.id,
                        probe_exc,
                    )
                    details["inbox_unread_excel_probe"] = None
                    details["other_senders_sample"] = []

            self.db.flush()
            logger.info(
                "Outlook sync listed unread | job={} | user_email={} | mailbox={} | found={} | max_messages={} | inbox_probe={}",
                job.id,
                user_email,
                mailbox,
                len(messages),
                sync_req.max_messages,
                details.get("inbox_unread_excel_probe"),
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
                            user_id=user_id,
                            user_role=user_role,
                        )
                    # Ingest savepoint released successfully — business data is durable here.
                    if sync_req.mark_as_read and _should_mark_graph_read(result):
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
                    elif sync_req.mark_as_read and not _should_mark_graph_read(result):
                        result["mark_as_read_ok"] = False
                        result["mark_as_read_skipped"] = str(result.get("status") or "")
                        logger.info(
                            "Skipped Graph mark-as-read | message_id={} | status={} | reason=not_ready_for_mark",
                            message_id,
                            result.get("status"),
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

            # Recovery: prior worker bugs marked Graph read then rolled back DB rows.
            # Also re-try invalid_subject rows now that comma subjects are accepted.
            if user_email:
                recovered = self._recover_sender_messages(
                    mailbox=mailbox,
                    user_email=user_email,
                    already_seen={m.get("id") for m in messages if m.get("id")},
                    max_messages=max(10, int(sync_req.max_messages or 5)),
                    mark_as_read=sync_req.mark_as_read,
                    actor=actor,
                    user_id=user_id,
                    user_role=user_role,
                    details=details,
                    job=job,
                )
                if recovered:
                    details["recovered_count"] = recovered
                    job.emails_found = int(job.emails_found or 0) + recovered
                    details["emails_found"] = job.emails_found

            if job.failures and job.emails_processed:
                job.status = SyncStatus.PARTIAL.value
            elif job.failures and not job.emails_processed:
                job.status = SyncStatus.FAILED.value
            else:
                job.status = SyncStatus.COMPLETED.value

            details["result_message"] = _sync_result_message(
                user_email=user_email,
                emails_found=job.emails_found,
                emails_processed=job.emails_processed,
                reports_created=job.reports_created,
                failures=job.failures,
                status=job.status,
                details=details,
            )
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
            success_count = int(job.emails_processed or 0)
            failure_count = int(job.failures or 0)
            if success_count == 0 and failure_count == 0:
                audit_details = "No new emails found"
            else:
                audit_details = f"{success_count} new emails synchronized successfully"
            self.audit.log(
                AuditTrailCreate(
                    user_name=triggered_by_label,
                    action=audit_action,
                    details=audit_details,
                    entity_type="sync_job",
                    entity_id=str(job.id),
                    module="Emails",
                    status=status_badge,
                    user_id=user_id,
                    extra_metadata={
                        "start_time": started_at.isoformat() if started_at else None,
                        "end_time": job.completed_at.isoformat() if job.completed_at else None,
                        "triggered_by": triggered_by_label,
                        "emails_processed": int(job.emails_processed or 0),
                        "success_count": success_count,
                        "failure_count": failure_count,
                        "emails_found": job.emails_found,
                        "sync_trigger": sync_trigger,
                        "user_email": user_email,
                    },
                )
            )
            if is_automated and job.status != SyncStatus.FAILED.value:
                try:
                    from app.services.outlook_auto_sync_scheduler import record_auto_sync_success

                    record_auto_sync_success(job.completed_at)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed recording auto-sync success timestamp")
            logger.info(
                "Sync Completed | job={} | user_email={} | status={} | processed={} | failures={} | warnings={} | records={}",
                job.id,
                user_email,
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
            details["result_message"] = f"Outlook sync failed: {exc}"
            job.completed_at = utc_now()
            job.details = details
            self.db.flush()
            self.db.refresh(job)
            self.audit.log(
                AuditTrailCreate(
                    user_name=triggered_by_label,
                    action=audit_action,
                    details=f"Outlook sync failed: {exc}",
                    entity_type="sync_job",
                    entity_id=str(job.id),
                    module="Emails",
                    status=AuditStatus.FAILED.value,
                    user_id=user_id,
                    extra_metadata={
                        "start_time": started_at.isoformat() if started_at else None,
                        "end_time": job.completed_at.isoformat() if job.completed_at else None,
                        "triggered_by": triggered_by_label,
                        "emails_processed": int(job.emails_processed or 0),
                        "success_count": 0,
                        "failure_count": int(job.failures or 0) + 1,
                        "sync_trigger": sync_trigger,
                        "user_email": user_email,
                    },
                )
            )
            logger.exception("Outlook sync failed | job={} | user_email={} | stage=sync | error={}", job.id, user_email, exc)
            if isinstance(exc, GraphAPIError):
                raise
            raise GraphAPIError(f"Outlook sync failed: {exc}") from exc

    def sync(self, request: OutlookSyncRequest, *, actor: str = "system") -> SyncJob:
        """Run a full Outlook sync (legacy / backward compatibility entry point)."""
        return self.sync_for_user(request=request, actor=actor)

    @staticmethod
    def _email_has_excel(email: EmailMessage) -> bool:
        for att in email.attachments or []:
            if getattr(att, "is_deleted", False):
                continue
            if att.is_excel or (att.file_name or "").lower().endswith((".xlsx", ".xlsm", ".xls")):
                return True
        return False

    def _email_needs_recovery(
        self, message: Dict[str, Any], existing: Optional[EmailMessage]
    ) -> bool:
        """True when Graph has the message but our DB never finished a usable extract."""
        if existing is None:
            return True
        if existing.process_status == EmailProcessStatus.INVALID_SUBJECT.value:
            return True
        if existing.process_status in {
            EmailProcessStatus.UNREAD.value,
            EmailProcessStatus.DOWNLOADED.value,
            EmailProcessStatus.PARSED.value,
            EmailProcessStatus.FAILED.value,
        } and not self._email_has_excel(existing):
            return True
        return False

    def _recover_sender_messages(
        self,
        *,
        mailbox: str,
        user_email: str,
        already_seen: set,
        max_messages: int,
        mark_as_read: bool,
        actor: str,
        user_id: Optional[int],
        user_role: Optional[str],
        details: Dict[str, Any],
        job: SyncJob,
    ) -> int:
        """
        Re-ingest recent FROM-sender messages that Graph already shows as read
        (or that exist in DB as invalid_subject) after a prior worker rollback.
        """
        try:
            recent = self.graph.list_messages(
                mailbox=mailbox,
                top=max_messages,
                has_attachments=True,
                sender_email=user_email,
                unread_only=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Sender recovery list failed | mailbox={} | sender={} | err={}",
                mailbox,
                user_email,
                exc,
            )
            return 0

        recovered = 0
        for message in recent:
            message_id = message.get("id")
            if not message_id or message_id in already_seen:
                continue
            existing = self._find_existing_email(message)
            if not self._email_needs_recovery(message, existing):
                continue
            try:
                with self.db.begin_nested():
                    result = self._process_message(
                        message,
                        mailbox=mailbox,
                        mark_as_read=False,
                        actor=actor,
                        user_id=user_id,
                        user_role=user_role,
                    )
                if mark_as_read and _should_mark_graph_read(result):
                    email = self._email_for_mark_read(message, result)
                    if email is not None:
                        mark_ok = self._ensure_marked_read(
                            email,
                            graph_id=str(message_id),
                            mailbox=mailbox,
                            reason="recovery_post_ingest",
                        )
                        result["mark_as_read_ok"] = mark_ok
                result["recovered"] = True
                details.setdefault("processed", []).append(result)
                job.emails_processed += 1
                job.attachments_downloaded += int(result.get("attachments_downloaded", 0))
                job.reports_created += int(result.get("reports_created", 0))
                job.records_inserted += int(result.get("records_inserted", 0))
                job.duplicates_skipped += int(result.get("duplicates_skipped", 0))
                recovered += 1
                logger.info(
                    "Recovered sender message | message_id={} | email_id={} | status={}",
                    message_id,
                    result.get("email_id"),
                    result.get("status"),
                )
            except Exception as exc:  # noqa: BLE001
                job.failures += 1
                details.setdefault("failures", []).append(
                    {"message_id": message_id, "error": str(exc), "recovered": True}
                )
                logger.exception(
                    "Recovery processing failed | message_id={} | error={}",
                    message_id,
                    exc,
                )
        return recovered

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
        reporting_quarter: Optional[str] = None,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None,
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

        from app.services.email_subject_service import EmailSubjectService

        EmailSubjectService(self.db).apply_to_email(email, actor=actor)
        if not email.subject_valid:
            return {
                "message_id": graph_id,
                "email_id": email.id,
                "status": EmailProcessStatus.INVALID_SUBJECT.value,
                "attachments_downloaded": 0,
                "reports_created": 0,
                "records_inserted": 0,
                "duplicates_skipped": 0,
                "mark_as_read_ok": None,
            }

        # Segment Authorization Check for non-admin user
        if email.parsed_segment and user_id and (user_role or "").lower() not in {"admin", "super_admin"}:
            from app.repositories.user_segment_repository import UserSegmentRepository

            assigned_segs = UserSegmentRepository(self.db).list_segments_for_user(user_id)
            clean_assigned = [s.strip().casefold() for s in assigned_segs]
            parsed_seg_clean = (email.parsed_segment or "").strip().casefold()

            if parsed_seg_clean not in clean_assigned:
                email.process_status = EmailProcessStatus.INVALID_SUBJECT.value
                email.error_message = f"Segment '{email.parsed_segment}' is not assigned to user ID {user_id}"
                self.db.flush()
                logger.warning(
                    "Segment authorization failed | email_id={} | segment={} | user_id={}",
                    email.id,
                    email.parsed_segment,
                    user_id,
                )
                return {
                    "message_id": graph_id,
                    "email_id": email.id,
                    "status": "segment_unauthorized",
                    "attachments_downloaded": 0,
                    "reports_created": 0,
                    "records_inserted": 0,
                    "duplicates_skipped": 0,
                    "mark_as_read_ok": None,
                }

        attachments = self.graph.list_attachments(graph_id, mailbox=mailbox)
        excel_attachments = [a for a in attachments if GraphClient.is_excel_attachment(a)]
        from app.services.erp_ingest_service import MAX_EXCEL_ATTACHMENTS_PER_EMAIL

        if len(excel_attachments) > MAX_EXCEL_ATTACHMENTS_PER_EMAIL:
            logger.warning(
                "Excel attachments capped | message_id={} | found={} | cap={}",
                graph_id,
                len(excel_attachments),
                MAX_EXCEL_ATTACHMENTS_PER_EMAIL,
            )
            excel_attachments = excel_attachments[:MAX_EXCEL_ATTACHMENTS_PER_EMAIL]
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
            # Fast sync: download only. Accuracy scoring runs in background queue
            # (Python layouts first, then LLM header fallback when needed).
            email.confidence_score = 0
            email.error_message = None
            self.db.flush()

            # Download only — import happens after admin Preview / Approve.
            any_success = True
            logger.info(
                "Attachment downloaded | message_id={} | file={}",
                graph_id,
                file_name,
            )

        if any_success:
            try:
                from app.services.erp_score_queue import enqueue_email_score

                enqueue_email_score(int(email.id), allow_llm=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ERP score enqueue failed | email_id={} | err={}",
                    email.id,
                    exc,
                )

        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.SYNCED,
                details=(
                    f"ERP Email Synced | email_id={email.id} | "
                    f"subject={email.subject} | attachments={attachments_downloaded}"
                ),
                entity_type="email",
                entity_id=str(email.id),
                module="Email Extraction",
                status="Success",
                extra_metadata={
                    "attachments_downloaded": attachments_downloaded,
                    "sender_email": email.sender_email,
                },
            )
        )

        mark_ok = None
        # Keep status as downloaded until preview/import; do not mark Graph read yet
        # (mark-as-read still available after successful import via sync option if desired)
        if any_success or duplicates_skipped:
            email.error_message = None
            self.db.flush()
            if mark_as_read:
                mark_ok = self._ensure_marked_read(
                    email,
                    graph_id=graph_id,
                    mailbox=mailbox,
                    reason="download_success",
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
