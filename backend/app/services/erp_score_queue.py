"""Background ERP accuracy scoring queue (Python first, LLM fallback).

Sync downloads Excel quickly and enqueues scoring so Outlook sync stays fast.
A single worker thread processes jobs FIFO — safe for UAT / private network.

Scores up to ``MAX_EXCEL_ATTACHMENTS_PER_EMAIL`` workbooks per email; the
email-level accuracy is the **minimum** of those scores so batch consolidate
only proceeds when every attachment is ready.

Every job ends as completed, failed, or human review. Scoring is never left on.
"""

from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.core.logging import get_logger
from app.database.session import SessionLocal
from app.enums import EmailProcessStatus

logger = get_logger(__name__)

_q: "queue.Queue[dict]" = queue.Queue()
_pending: Set[int] = set()
_lock = threading.Lock()
_worker_started = False

SCORE_TIMEOUT_SECONDS = 30
HUMAN_REVIEW_BELOW = 70
_TERMINAL_SKIP = {
    EmailProcessStatus.INSERTED.value,
    EmailProcessStatus.MARKED_READ.value,
    EmailProcessStatus.SKIPPED.value,
    EmailProcessStatus.INVALID_SUBJECT.value,
    EmailProcessStatus.FAILED.value,
    EmailProcessStatus.HUMAN_REVIEW.value,
    EmailProcessStatus.INCREMENTAL_REVIEW.value,
    EmailProcessStatus.DUPLICATE_UPLOAD.value,
}


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
            _persist_terminal(
                email_id,
                process_status=EmailProcessStatus.FAILED.value,
                confidence=0,
                error_message=_failure_reason(exc),
            )
        finally:
            with _lock:
                _pending.discard(email_id)
            _q.task_done()


def _failure_reason(exc: BaseException) -> str:
    text = str(exc).strip() or "Could not detect structured sales table"
    return text[:500]


def _persist_terminal(
    email_id: int,
    *,
    process_status: str,
    confidence: int,
    error_message: Optional[str],
    mapping_source: Optional[str] = None,
) -> None:
    """Commit the terminal score even when the worker thread was abandoned."""
    if email_id <= 0:
        return
    db = SessionLocal()
    try:
        from app.models.email_message import EmailMessage
        from sqlalchemy import select

        email = db.scalar(
            select(EmailMessage).where(
                EmailMessage.id == email_id,
                EmailMessage.is_deleted.is_(False),
            )
        )
        if email is None:
            return
        if (email.process_status or "") in {
            EmailProcessStatus.INSERTED.value,
            EmailProcessStatus.MARKED_READ.value,
        }:
            return
        email.process_status = process_status
        email.confidence_score = int(confidence)
        email.error_message = error_message
        if mapping_source:
            email.mapping_source = mapping_source
        db.commit()
        logger.info(
            "ERP score terminal | email_id={} | status={} | confidence={} | reason={}",
            email_id,
            process_status,
            email.confidence_score,
            error_message or "",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("ERP score terminal commit failed | email_id={} | err={}", email_id, exc)
    finally:
        db.close()


def _score_email(email_id: int, *, allow_llm: bool = True) -> None:
    """Score one email. The finally path always leaves a terminal status."""
    if email_id <= 0:
        return
    if not _mark_scoring(email_id):
        return

    done = threading.Event()
    commit_lock = threading.Lock()

    def work() -> None:
        db = SessionLocal()
        try:
            outcome = _run_score(db, email_id, allow_llm=allow_llm)
            with commit_lock:
                if done.is_set():
                    db.rollback()
                    return
                _apply_outcome(db, email_id, outcome)
                db.commit()
                done.set()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("ERP score parse failed | email_id={} | err={}", email_id, exc)
            with commit_lock:
                if done.is_set():
                    return
                _apply_outcome(
                    db,
                    email_id,
                    {
                        "process_status": EmailProcessStatus.FAILED.value,
                        "confidence": 0,
                        "error_message": _failure_reason(exc),
                        "mapping_source": None,
                    },
                )
                db.commit()
                done.set()
        finally:
            db.close()

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="erp-score-job")
    future = pool.submit(work)
    try:
        future.result(timeout=SCORE_TIMEOUT_SECONDS)
    except FuturesTimeout:
        logger.warning("ERP score timeout | email_id={} | limit={}s", email_id, SCORE_TIMEOUT_SECONDS)
        with commit_lock:
            if not done.is_set():
                _persist_terminal(
                    email_id,
                    process_status=EmailProcessStatus.FAILED.value,
                    confidence=0,
                    error_message="Scoring timeout",
                )
                done.set()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ERP score worker error | email_id={} | err={}", email_id, exc)
        with commit_lock:
            if not done.is_set():
                _persist_terminal(
                    email_id,
                    process_status=EmailProcessStatus.FAILED.value,
                    confidence=0,
                    error_message=_failure_reason(exc),
                )
                done.set()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        if not done.is_set():
            _persist_terminal(
                email_id,
                process_status=EmailProcessStatus.FAILED.value,
                confidence=0,
                error_message="Could not detect structured sales table",
            )
            done.set()


def _mark_scoring(email_id: int) -> bool:
    db = SessionLocal()
    try:
        from app.models.email_message import EmailMessage
        from sqlalchemy import select

        email = db.scalar(
            select(EmailMessage).where(
                EmailMessage.id == email_id,
                EmailMessage.is_deleted.is_(False),
            )
        )
        if email is None:
            return False
        status = (email.process_status or "").lower()
        if status in _TERMINAL_SKIP:
            return False
        if status == EmailProcessStatus.PARSED.value and int(email.confidence_score or 0) >= HUMAN_REVIEW_BELOW:
            return False
        email.process_status = EmailProcessStatus.SCORING.value
        db.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("ERP score start failed | email_id={} | err={}", email_id, exc)
        return False
    finally:
        db.close()


def _apply_outcome(db: Any, email_id: int, outcome: Dict[str, Any]) -> None:
    from app.models.email_message import EmailMessage
    from sqlalchemy import select

    email = db.scalar(
        select(EmailMessage).where(
            EmailMessage.id == email_id,
            EmailMessage.is_deleted.is_(False),
        )
    )
    if email is None or outcome.get("skip"):
        return
    if (email.process_status or "") in {
        EmailProcessStatus.INSERTED.value,
        EmailProcessStatus.MARKED_READ.value,
    }:
        return
    email.process_status = outcome["process_status"]
    email.confidence_score = int(outcome["confidence"])
    email.error_message = outcome.get("error_message")
    if outcome.get("mapping_source"):
        email.mapping_source = outcome["mapping_source"]
    logger.info(
        "ERP score terminal | email_id={} | status={} | confidence={} | reason={}",
        email_id,
        email.process_status,
        email.confidence_score,
        email.error_message or "",
    )


def _run_score(db: Any, email_id: int, *, allow_llm: bool) -> Dict[str, Any]:
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
    if email is None or (email.process_status or "") in {
        EmailProcessStatus.INSERTED.value,
        EmailProcessStatus.MARKED_READ.value,
    }:
        return {
            "process_status": email.process_status if email is not None else EmailProcessStatus.FAILED.value,
            "confidence": int(email.confidence_score or 0) if email is not None else 0,
            "error_message": None,
            "mapping_source": None,
            "skip": True,
        }

    excels: List[Any] = []
    for att in email.attachments or []:
        if getattr(att, "is_deleted", False):
            continue
        if att.is_excel or (att.file_name or "").lower().endswith(
            (".xlsx", ".xlsm", ".xls", ".pdf", ".docx")
        ):
            excels.append(att)
        if len(excels) >= MAX_EXCEL_ATTACHMENTS_PER_EMAIL:
            break

    if not excels:
        return {
            "process_status": EmailProcessStatus.FAILED.value,
            "confidence": 0,
            "error_message": "Could not detect structured sales table",
            "mapping_source": None,
        }

    scores: List[float] = []
    sources: List[str] = []
    failed_names: List[str] = []
    parser = ERPParserService()

    for excel in excels:
        if not excel.file_path or not Path(excel.file_path).is_file():
            failed_names.append(excel.file_name or "?")
            continue
        try:
            preview = parser.preview(
                Path(excel.file_path),
                allow_llm_fallback=allow_llm,
                distributor_label=email.parsed_distributor or "",
                subject=email.subject,
                reporting_quarter=(email.detected_quarter or None),
            )
            overall = float((preview.get("confidence") or {}).get("overall") or 0)
            scores.append(overall)
            sources.append(str(preview.get("mapping_source") or "python").lower())
            logger.info(
                "ERP score attachment | email_id={} | file={} | confidence={} | source={}",
                email_id,
                excel.file_name,
                int(round(overall)),
                sources[-1],
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
        return {
            "process_status": EmailProcessStatus.FAILED.value,
            "confidence": 0,
            "error_message": "Could not detect structured sales table",
            "mapping_source": None,
        }

    mapping_source = "llm" if any(src == "llm" for src in sources) else (sources[0] if sources else "python")
    _remember_quarter(db, email, excels, allow_llm=allow_llm)
    confidence = int(round(min(scores)))
    note = None
    if failed_names:
        note = (
            f"Scored {len(scores)}/{len(excels)} workbook(s); "
            f"failed: {', '.join(failed_names[:3])}"
        )
    if confidence <= 0:
        process_status = EmailProcessStatus.FAILED.value
        note = note or "Could not detect structured sales table"
    elif confidence < HUMAN_REVIEW_BELOW:
        process_status = EmailProcessStatus.HUMAN_REVIEW.value
    else:
        process_status = EmailProcessStatus.PARSED.value
    return {
        "process_status": process_status,
        "confidence": confidence,
        "error_message": note,
        "mapping_source": mapping_source,
    }


def _remember_quarter(db: Any, email: Any, excels: List[Any], *, allow_llm: bool) -> None:
    """Keep subject period. Fill a missing quarter from the primary workbook."""
    try:
        from app.erp_parser.quarter_detector import detect_reporting_quarter
        from app.schemas.audit import AuditTrailCreate
        from app.services.audit_service import AuditService

        primary = excels[0]
        if not primary.file_path or (email.detected_quarter or "").strip():
            return
        qhit = detect_reporting_quarter(Path(primary.file_path), allow_llm_fallback=allow_llm)
        label = (qhit or {}).get("reporting_quarter")
        if not label:
            return
        email.detected_quarter = str(label)
        AuditService(db).log(
            AuditTrailCreate(
                user_name="system",
                action="Quarter Detected",
                details=(
                    f"Quarter detected for email_id={email.id} | quarter={label} | "
                    f"confidence={qhit.get('confidence')}"
                ),
                entity_type="email",
                entity_id=str(email.id),
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
        logger.warning("Quarter detect skipped | email_id={} | err={}", getattr(email, "id", None), exc)


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
