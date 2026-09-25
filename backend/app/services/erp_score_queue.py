"""Background ERP accuracy scoring queue (Python first, LLM fallback).

Sync downloads Excel quickly and enqueues scoring so Outlook sync stays fast.
A single worker thread processes jobs FIFO — safe for UAT / private network.

Scores up to ``MAX_EXCEL_ATTACHMENTS_PER_EMAIL`` workbooks per email; the
email-level accuracy is the **minimum** of those scores so batch consolidate
only proceeds when every attachment is ready.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any, List, Set

from app.core.logging import get_logger
from app.database.session import SessionLocal
from app.enums import EmailProcessStatus

logger = get_logger(__name__)

_q: "queue.Queue[dict]" = queue.Queue()
_pending: Set[int] = set()
_lock = threading.Lock()
_worker_started = False


def enqueue_email_score(email_id: int, *, allow_llm: bool = True) -> bool:
    """
    Queue an email Excel for accuracy scoring.

    Returns False if already queued/in-flight for this email_id.
    """
    _ensure_worker()
    with _lock:
        if email_id in _pending:
            return False
        _pending.add(email_id)
    _q.put({"email_id": int(email_id), "allow_llm": bool(allow_llm)})
    logger.info("ERP score queued | email_id={} | allow_llm={}", email_id, allow_llm)
    return True


def pending_count() -> int:
    with _lock:
        return len(_pending)


def is_pending(email_id: int) -> bool:
    with _lock:
        return email_id in _pending


def _ensure_worker() -> None:
    global _worker_started
    with _lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker_loop, name="erp-score-worker", daemon=True)
        t.start()
        _worker_started = True
        logger.info("ERP score worker started")


def _worker_loop() -> None:
    while True:
        job = _q.get()
        email_id = int(job.get("email_id") or 0)
        allow_llm = bool(job.get("allow_llm", True))
        try:
            _score_email(email_id, allow_llm=allow_llm)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ERP score job failed | email_id={} | err={}", email_id, exc)
        finally:
            with _lock:
                _pending.discard(email_id)
            _q.task_done()


def _score_email(email_id: int, *, allow_llm: bool = True) -> None:
    if email_id <= 0:
        return
    db = SessionLocal()
    try:
        from app.erp_parser import ERPParserService
        from app.models.email_message import EmailMessage
        from app.services.erp_ingest_service import MAX_EXCEL_ATTACHMENTS_PER_EMAIL
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        email = db.scalar(
            select(EmailMessage)
            .options(selectinload(EmailMessage.attachments))
            .where(EmailMessage.id == email_id, EmailMessage.is_deleted.is_(False))
        )
        if email is None:
            return

        # Skip if already imported / skipped
        status = (email.process_status or "").lower()
        if status in {
            EmailProcessStatus.INSERTED.value,
            EmailProcessStatus.MARKED_READ.value,
            EmailProcessStatus.SKIPPED.value,
        }:
            return
        if email.confidence_score is not None and int(email.confidence_score) >= 75:
            return

        excels: List[Any] = []
        for att in email.attachments or []:
            if getattr(att, "is_deleted", False):
                continue
            if att.is_excel or (att.file_name or "").lower().endswith((".xlsx", ".xlsm", ".xls")):
                excels.append(att)
            if len(excels) >= MAX_EXCEL_ATTACHMENTS_PER_EMAIL:
                break

        if not excels:
            email.confidence_score = 0
            email.error_message = "No Excel attachment on disk for scoring"
            db.commit()
            return

        scores: List[float] = []
        sources: List[str] = []
        failed_names: List[str] = []
        parser = ERPParserService()

        for excel in excels:
            if not excel.file_path:
                failed_names.append(excel.file_name or "?")
                continue
            path = Path(excel.file_path)
            if not path.is_file():
                failed_names.append(excel.file_name or "?")
                continue
            try:
                preview = parser.preview(
                    path,
                    allow_llm_fallback=allow_llm,
                    distributor_label=email.parsed_distributor or "",
                    subject=email.subject,
                    reporting_quarter=(email.detected_quarter or None),
                )
                overall = float((preview.get("confidence") or {}).get("overall") or 0)
                scores.append(overall)
                src = str(preview.get("mapping_source") or "python").lower()
                sources.append(src)
                logger.info(
                    "ERP score attachment | email_id={} | file={} | confidence={} | source={}",
                    email_id,
                    excel.file_name,
                    int(round(overall)),
                    src,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ERP score parse failed | email_id={} | file={} | err={}",
                    email_id,
                    excel.file_name,
                    exc,
                )
                failed_names.append(excel.file_name or "?")

        if not scores:
            email.confidence_score = 0
            if status in {"", EmailProcessStatus.UNREAD.value}:
                email.process_status = EmailProcessStatus.DOWNLOADED.value
            email.error_message = (
                "Could not auto-score Excel attachment(s). Open Preview to map columns manually."
            )
            db.commit()
            return

        email.mapping_source = "llm" if any(s == "llm" for s in sources) else (sources[0] if sources else "python")

        # Detect reporting quarter from primary workbook only when subject has no period
        try:
            from app.erp_parser.quarter_detector import detect_reporting_quarter
            from app.services.audit_service import AuditService
            from app.schemas.audit import AuditTrailCreate

            primary = excels[0]
            if primary.file_path and not (email.detected_quarter or "").strip():
                qhit = detect_reporting_quarter(
                    Path(primary.file_path),
                    allow_llm_fallback=allow_llm,
                )
                label = (qhit or {}).get("reporting_quarter")
                if label:
                    email.detected_quarter = str(label)
                    AuditService(db).log(
                        AuditTrailCreate(
                            user_name="system",
                            action="Quarter Detected",
                            details=(
                                f"Quarter detected for email_id={email_id} | quarter={label} | "
                                f"confidence={qhit.get('confidence')}"
                            ),
                            entity_type="email",
                            entity_id=str(email_id),
                            module="Email Extraction",
                            status="Success",
                            extra_metadata={
                                "segment": email.parsed_segment,
                                "reporting_quarter": label,
                                "confidence": qhit.get("confidence"),
                                "source": qhit.get("source"),
                            },
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Quarter detect skipped | email_id={} | err={}", email_id, exc)

        # Email-level accuracy = worst workbook so batch only runs when all are ready
        email.confidence_score = int(round(min(scores)))
        if email.process_status != EmailProcessStatus.INVALID_SUBJECT.value:
            email.process_status = EmailProcessStatus.PARSED.value
        if failed_names:
            email.error_message = (
                f"Scored {len(scores)}/{len(excels)} workbook(s); "
                f"failed: {', '.join(failed_names[:3])}"
            )
        else:
            email.error_message = None
        logger.info(
            "ERP score complete | email_id={} | workbooks={} | min_confidence={} | source={} | scores={}",
            email_id,
            len(scores),
            email.confidence_score,
            email.mapping_source,
            [int(round(s)) for s in scores],
        )
        db.commit()
    finally:
        db.close()


def reset_for_tests() -> None:
    """Clear queue state (unit tests)."""
    global _worker_started
    with _lock:
        _pending.clear()
        while not _q.empty():
            try:
                _q.get_nowait()
                _q.task_done()
            except Exception:  # noqa: BLE001
                break
