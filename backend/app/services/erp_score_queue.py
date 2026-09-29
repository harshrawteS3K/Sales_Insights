"""Background ERP accuracy scoring queue (Python first, LLM fallback).

Sync downloads Excel quickly and enqueues scoring so Outlook sync stays fast.
A single worker thread processes jobs FIFO — safe for UAT / private network.

Scores up to ``MAX_EXCEL_ATTACHMENTS_PER_EMAIL`` workbooks per email; the
email-level accuracy is the **minimum of successful attachment scores**.

Critical rule: a successful parse (rows > 0, confidence >= import threshold)
is NEVER overwritten with confidence=0 because quarter detection, LLM
enrichment, or a soft job ceiling timed out.
"""

from __future__ import annotations

import copy
import queue
import threading
import time
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

# Soft ceiling for the whole email job. Attachments are checkpointed as they
# finish so a late timeout cannot erase successful parses.
SCORE_TIMEOUT_SECONDS = 180
HUMAN_REVIEW_BELOW = 70
IMPORT_THRESHOLD = HUMAN_REVIEW_BELOW
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
            _persist_terminal_preserving_success(
                email_id,
                fallback_status=EmailProcessStatus.FAILED.value,
                fallback_confidence=0,
                error_message=_failure_reason(exc),
            )
        finally:
            with _lock:
                _pending.discard(email_id)
            _q.task_done()


def _failure_reason(exc: BaseException) -> str:
    text = str(exc).strip() or "Could not detect structured sales table"
    return text[:500]


def _empty_progress() -> Dict[str, Any]:
    return {
        "attachments": [],  # per-file results
        "quarter_status": "pending",
        "warnings": [],
    }


def _successful_scores(progress: Dict[str, Any]) -> List[float]:
    return [
        float(item["confidence"])
        for item in progress.get("attachments") or []
        if item.get("status") == "success" and float(item.get("confidence") or 0) > 0
    ]


def _outcome_from_progress(progress: Dict[str, Any]) -> Dict[str, Any]:
    scores = _successful_scores(progress)
    failed = [
        str(item.get("file") or "?")
        for item in progress.get("attachments") or []
        if item.get("status") != "success"
    ]
    sources = [
        str(item.get("mapping_source") or "python").lower()
        for item in progress.get("attachments") or []
        if item.get("status") == "success"
    ]
    warnings = list(progress.get("warnings") or [])
    quarter = str(progress.get("quarter_status") or "")
    if quarter in {"warning", "unresolved", "timeout"}:
        warnings.append(f"Quarter detection: {quarter}")

    if not scores:
        note = "; ".join(warnings) if warnings else "Could not detect structured sales table"
        if failed:
            note = f"All attachments failed: {', '.join(failed[:3])}"
        return {
            "process_status": EmailProcessStatus.FAILED.value,
            "confidence": 0,
            "error_message": note[:500],
            "mapping_source": None,
        }

    mapping_source = "llm" if any(src == "llm" for src in sources) else (sources[0] if sources else "python")
    confidence = int(round(min(scores)))
    note_parts = list(warnings)
    if failed:
        note_parts.append(
            f"Scored {len(scores)}/{len(scores) + len(failed)} workbook(s); "
            f"failed: {', '.join(failed[:3])}"
        )
    note = "; ".join(note_parts) if note_parts else None

    if confidence < IMPORT_THRESHOLD:
        process_status = EmailProcessStatus.HUMAN_REVIEW.value
    else:
        process_status = EmailProcessStatus.PARSED.value
    return {
        "process_status": process_status,
        "confidence": confidence,
        "error_message": (note[:500] if note else None),
        "mapping_source": mapping_source,
    }


def _persist_terminal(
    email_id: int,
    *,
    process_status: str,
    confidence: int,
    error_message: Optional[str],
    mapping_source: Optional[str] = None,
) -> None:
    """Commit a terminal score. Never downgrades a retained successful parse to 0."""
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

        outcome = {
            "process_status": process_status,
            "confidence": int(confidence),
            "error_message": error_message,
            "mapping_source": mapping_source,
        }
        outcome = _protect_successful_parse(email, outcome)
        email.process_status = outcome["process_status"]
        email.confidence_score = int(outcome["confidence"])
        email.error_message = outcome.get("error_message")
        if outcome.get("mapping_source"):
            email.mapping_source = outcome["mapping_source"]
        db.commit()
        logger.info(
            "ERP score terminal | email_id={} | status={} | confidence={} | reason={}",
            email_id,
            email.process_status,
            email.confidence_score,
            email.error_message or "",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("ERP score terminal commit failed | email_id={} | err={}", email_id, exc)
    finally:
        db.close()


def _protect_successful_parse(email: Any, outcome: Dict[str, Any]) -> Dict[str, Any]:
    """
    A parser result with confidence >= import threshold must never become 0/failed
    solely because enrichment timed out or failed.
    """
    old_conf = int(email.confidence_score or 0)
    old_status = (email.process_status or "").strip()
    new_conf = int(outcome.get("confidence") or 0)
    new_status = str(outcome.get("process_status") or "")

    retained_success = old_conf >= IMPORT_THRESHOLD and old_status in {
        EmailProcessStatus.PARSED.value,
        EmailProcessStatus.SCORING.value,
        EmailProcessStatus.HUMAN_REVIEW.value,
    }
    wiping = new_conf <= 0 or new_status == EmailProcessStatus.FAILED.value
    if retained_success and wiping and new_conf < old_conf:
        warning = str(outcome.get("error_message") or "").strip()
        retained_note = "Parser result retained after enrichment timeout/failure"
        merged = f"{warning}; {retained_note}".strip("; ").strip() if warning else retained_note
        logger.warning(
            "ERP score protect success | email_id={} | keep_confidence={} | rejected_status={} | rejected_confidence={}",
            getattr(email, "id", None),
            old_conf,
            new_status,
            new_conf,
        )
        return {
            "process_status": (
                EmailProcessStatus.PARSED.value
                if old_conf >= IMPORT_THRESHOLD
                else EmailProcessStatus.HUMAN_REVIEW.value
            ),
            "confidence": old_conf,
            "error_message": merged[:500],
            "mapping_source": getattr(email, "mapping_source", None) or outcome.get("mapping_source"),
        }
    return outcome


def _persist_terminal_preserving_success(
    email_id: int,
    *,
    fallback_status: str,
    fallback_confidence: int,
    error_message: Optional[str],
    progress: Optional[Dict[str, Any]] = None,
) -> None:
    """On timeout/error: keep successful attachment scores when available."""
    if progress is not None:
        scores = _successful_scores(progress)
        if scores:
            outcome = _outcome_from_progress(progress)
            warnings = list(progress.get("warnings") or [])
            if error_message:
                warnings.append(error_message)
            if warnings:
                prior = outcome.get("error_message") or ""
                merged = "; ".join([p for p in (prior, *warnings) if p])
                outcome["error_message"] = merged[:500]
            _persist_terminal(
                email_id,
                process_status=outcome["process_status"],
                confidence=int(outcome["confidence"]),
                error_message=outcome.get("error_message"),
                mapping_source=outcome.get("mapping_source"),
            )
            return
    _persist_terminal(
        email_id,
        process_status=fallback_status,
        confidence=fallback_confidence,
        error_message=error_message,
    )


def _checkpoint_progress(email_id: int, progress: Dict[str, Any]) -> None:
    """Persist best-so-far successful scores so a later timeout cannot wipe them."""
    scores = _successful_scores(progress)
    if not scores:
        return
    outcome = _outcome_from_progress(progress)
    # Stay in SCORING until the job finishes, but store confidence immediately.
    _persist_terminal(
        email_id,
        process_status=EmailProcessStatus.SCORING.value,
        confidence=int(outcome["confidence"]),
        error_message=outcome.get("error_message"),
        mapping_source=outcome.get("mapping_source"),
    )


def _score_email(email_id: int, *, allow_llm: bool = True) -> None:
    """Score one email. Successful parses are checkpointed; timeouts cannot wipe them."""
    if email_id <= 0:
        return
    if not _mark_scoring(email_id):
        return

    done = threading.Event()
    commit_lock = threading.Lock()
    progress_lock = threading.Lock()
    progress = _empty_progress()

    def work() -> None:
        db = SessionLocal()
        try:
            outcome = _run_score(
                db,
                email_id,
                allow_llm=allow_llm,
                progress=progress,
                progress_lock=progress_lock,
                on_attachment=lambda: _checkpoint_progress(email_id, copy.deepcopy(progress)),
            )
            with commit_lock:
                protected = outcome
                # Re-read email to protect against concurrent timeout write.
                from app.models.email_message import EmailMessage
                from sqlalchemy import select

                email = db.scalar(
                    select(EmailMessage).where(
                        EmailMessage.id == email_id,
                        EmailMessage.is_deleted.is_(False),
                    )
                )
                if email is not None:
                    protected = _protect_successful_parse(email, outcome)
                if done.is_set():
                    # Timeout already committed — only upgrade, never wipe success.
                    if int(protected.get("confidence") or 0) >= IMPORT_THRESHOLD:
                        _apply_outcome(db, email_id, protected)
                        db.commit()
                    else:
                        db.rollback()
                    return
                _apply_outcome(db, email_id, protected)
                db.commit()
                done.set()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("ERP score parse failed | email_id={} | err={}", email_id, exc)
            with progress_lock:
                snap = copy.deepcopy(progress)
            with commit_lock:
                if done.is_set():
                    return
                if _successful_scores(snap):
                    outcome = _outcome_from_progress(snap)
                    outcome["error_message"] = (
                        f"{outcome.get('error_message') or ''}; {_failure_reason(exc)}"
                    ).strip("; ")[:500]
                    _apply_outcome(db, email_id, outcome)
                else:
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
        logger.warning(
            "ERP score timeout | email_id={} | limit={}s | retaining_successful_parses={}",
            email_id,
            SCORE_TIMEOUT_SECONDS,
            bool(_successful_scores(progress)),
        )
        with progress_lock:
            snap = copy.deepcopy(progress)
            snap.setdefault("warnings", []).append("Scoring enrichment timed out")
        with commit_lock:
            if not done.is_set():
                _persist_terminal_preserving_success(
                    email_id,
                    fallback_status=EmailProcessStatus.FAILED.value,
                    fallback_confidence=0,
                    error_message="Scoring timeout",
                    progress=snap,
                )
                done.set()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ERP score worker error | email_id={} | err={}", email_id, exc)
        with progress_lock:
            snap = copy.deepcopy(progress)
        with commit_lock:
            if not done.is_set():
                _persist_terminal_preserving_success(
                    email_id,
                    fallback_status=EmailProcessStatus.FAILED.value,
                    fallback_confidence=0,
                    error_message=_failure_reason(exc),
                    progress=snap,
                )
                done.set()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        if not done.is_set():
            with progress_lock:
                snap = copy.deepcopy(progress)
            _persist_terminal_preserving_success(
                email_id,
                fallback_status=EmailProcessStatus.FAILED.value,
                fallback_confidence=0,
                error_message="Could not detect structured sales table",
                progress=snap,
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
    protected = _protect_successful_parse(email, outcome)
    email.process_status = protected["process_status"]
    email.confidence_score = int(protected["confidence"])
    email.error_message = protected.get("error_message")
    if protected.get("mapping_source"):
        email.mapping_source = protected["mapping_source"]
    logger.info(
        "ERP score terminal | email_id={} | status={} | confidence={} | reason={}",
        email_id,
        email.process_status,
        email.confidence_score,
        email.error_message or "",
    )


def _run_score(
    db: Any,
    email_id: int,
    *,
    allow_llm: bool,
    progress: Dict[str, Any],
    progress_lock: threading.Lock,
    on_attachment: Optional[Any] = None,
) -> Dict[str, Any]:
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
        with progress_lock:
            progress["quarter_status"] = "skipped"
        return {
            "process_status": EmailProcessStatus.FAILED.value,
            "confidence": 0,
            "error_message": "Could not detect structured sales table",
            "mapping_source": None,
        }

    parser = ERPParserService()

    for excel in excels:
        started = time.perf_counter()
        file_name = excel.file_name or "?"
        if not excel.file_path or not Path(excel.file_path).is_file():
            with progress_lock:
                progress["attachments"].append(
                    {
                        "file": file_name,
                        "status": "failed",
                        "confidence": 0,
                        "rows": 0,
                        "error": "missing file",
                    }
                )
            continue
        try:
            # parse_workbook only — do NOT use preview() here; preview runs
            # quarter LLM per file and can blow the job ceiling after success.
            result = parser.parse_workbook(
                Path(excel.file_path),
                allow_llm_fallback=allow_llm,
                distributor_label=email.parsed_distributor or "",
                subject=email.subject,
                reporting_quarter=(email.detected_quarter or None),
            )
            overall = float(result.overall_confidence or 0)
            rows_n = int(result.imported_rows or len(result.rows or []))
            source = str(result.mapping_source or "python").lower()
            breakdown = dict(result.confidence_breakdown or {})
            sheet = str(result.sheet_name or "")
            layout = str(breakdown.get("layout") or breakdown.get("parser_label") or "")
            duration = time.perf_counter() - started
            ok = rows_n > 0 and overall > 0
            with progress_lock:
                progress["attachments"].append(
                    {
                        "file": file_name,
                        "status": "success" if ok else "failed",
                        "confidence": overall,
                        "rows": rows_n,
                        "mapping_source": source,
                        "sheet": sheet,
                        "layout": layout,
                        "llm_used": bool(getattr(result, "llm_used", False) or source == "llm"),
                        "duration": round(duration, 2),
                    }
                )
            logger.info(
                "ERP Attachment Audit\n"
                "File : {}\n"
                "Sheets scanned : {}\n"
                "Selected sheet : {}\n"
                "Layout : {}\n"
                "Rows parsed : {}\n"
                "Deterministic confidence : {}\n"
                "LLM used : {}\n"
                "LLM reason : {}\n"
                "Quarter detection status : pending\n"
                "Final status : {}\n"
                "Duration : {:.2f} sec",
                file_name,
                len(result.candidate_sheets or []) or "?",
                sheet,
                layout,
                rows_n,
                int(round(overall)),
                "Yes" if source == "llm" else "No",
                breakdown.get("llm_reason") or "",
                "SUCCESS" if ok else "FAILED",
                duration,
            )
            logger.info(
                "ERP score attachment | email_id={} | file={} | confidence={} | rows={} | source={}",
                email_id,
                file_name,
                int(round(overall)),
                rows_n,
                source,
            )
            if on_attachment and ok:
                try:
                    on_attachment()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("ERP score checkpoint failed | email_id={} | err={}", email_id, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ERP score parse failed | email_id={} | file={} | err={}",
                email_id,
                file_name,
                exc,
            )
            with progress_lock:
                progress["attachments"].append(
                    {
                        "file": file_name,
                        "status": "failed",
                        "confidence": 0,
                        "rows": 0,
                        "error": _failure_reason(exc),
                    }
                )

    # Quarter detection is enrichment only — never fails the email score.
    q_status = _remember_quarter(db, email, excels, allow_llm=allow_llm)
    with progress_lock:
        progress["quarter_status"] = q_status
        for item in progress["attachments"]:
            if item.get("status") == "success":
                logger.info(
                    "ERP Attachment Audit (quarter)\nFile : {}\nQuarter detection status : {}\nFinal status : SUCCESS",
                    item.get("file"),
                    q_status,
                )

    return _outcome_from_progress(progress)


def _remember_quarter(db: Any, email: Any, excels: List[Any], *, allow_llm: bool) -> str:
    """
    Fill a missing quarter from the primary workbook.

    Deterministic first. LLM failure/empty response → warning only.
    Never raises into the score path.
    """
    try:
        from app.erp_parser.quarter_detector import detect_reporting_quarter
        from app.schemas.audit import AuditTrailCreate
        from app.services.audit_service import AuditService

        if (email.detected_quarter or "").strip():
            return "subject_or_existing"
        if not excels:
            return "skipped"
        primary = excels[0]
        if not primary.file_path:
            return "skipped"

        # Deterministic only first — avoids Bedrock empty-response delays.
        qhit = detect_reporting_quarter(Path(primary.file_path), allow_llm_fallback=False)
        label = (qhit or {}).get("reporting_quarter")
        source = str((qhit or {}).get("source") or "deterministic")
        if not label and allow_llm:
            try:
                qhit = detect_reporting_quarter(Path(primary.file_path), allow_llm_fallback=True)
                label = (qhit or {}).get("reporting_quarter")
                source = str((qhit or {}).get("source") or "llm")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LLM quarter detection failed | email_id={} | err={}",
                    getattr(email, "id", None),
                    exc,
                )
                return "warning"

        if not label:
            logger.info(
                "Quarter detection unresolved | email_id={} | parser results retained",
                getattr(email, "id", None),
            )
            return "unresolved"

        email.detected_quarter = str(label)
        AuditService(db).log(
            AuditTrailCreate(
                user_name="system",
                action="Quarter Detected",
                details=(
                    f"Quarter detected for email_id={email.id} | quarter={label} | "
                    f"confidence={qhit.get('confidence')} | source={source}"
                ),
                entity_type="email",
                entity_id=str(email.id),
                module="Email Extraction",
                status="Success",
                extra_metadata={
                    "segment": email.parsed_segment,
                    "reporting_quarter": label,
                    "confidence": qhit.get("confidence"),
                    "source": source,
                },
            )
        )
        return "deterministic" if source != "llm" else "llm"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quarter detect skipped | email_id={} | err={}", getattr(email, "id", None), exc)
        return "warning"


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
