"""Sequential bulk Outlook draft creation for distributors (job + polling)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.database.session import SessionLocal
from app.enums import AuditAction
from app.exceptions import GraphAPIError, ValidationAppError
from app.schemas.audit import AuditTrailCreate
from app.services.audit_service import AuditService
from app.services.template_generation_service import TemplateGenerationService
from app.utils.reporting_month import normalize_reporting_month

logger = get_logger(__name__)

_MAX_BATCH = 100
_lock = threading.Lock()
_jobs: Dict[str, "BulkEmailDraftJob"] = {}
_running_job_id: Optional[str] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_failure_reason(exc: BaseException) -> str:
    """User-facing failure reason (no tokens / stack traces)."""
    if isinstance(exc, ValidationAppError):
        msg = str(getattr(exc, "message", None) or exc)
        lower = msg.lower()
        if "email" in lower and (
            "not configured" in lower or "missing" in lower or "update the distributor" in lower
        ):
            return "Distributor email address is not configured."
        if "inactive" in lower or "deleted" in lower:
            return "Distributor is inactive."
        if "product master" in lower:
            return "Product Master is not available."
        # Keep other validation messages short and safe
        return msg.split(".")[0].strip()[:280] + ("." if not msg.endswith(".") else "")
    if isinstance(exc, GraphAPIError):
        return "Unable to create Outlook draft."
    return "Unable to create Outlook draft."


@dataclass
class BulkDraftItemResult:
    distributor_id: int
    distributor_name: str
    success: bool
    reason: Optional[str] = None
    draft_id: Optional[str] = None
    attachment_name: Optional[str] = None
    recipient: Optional[str] = None


@dataclass
class BulkEmailDraftJob:
    job_id: str
    status: str  # queued | running | completed | failed
    reporting_quarter: str
    distributor_ids: List[int]
    actor: str
    total: int
    processed: int = 0
    successful: int = 0
    failed: int = 0
    results: List[BulkDraftItemResult] = field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "reporting_quarter": self.reporting_quarter,
            "total": self.total,
            "processed": self.processed,
            "successful": self.successful,
            "failed": self.failed,
            "results": [
                {
                    "distributor_id": r.distributor_id,
                    "distributor_name": r.distributor_name,
                    "success": r.success,
                    "reason": r.reason,
                    "draft_id": r.draft_id,
                    "attachment_name": r.attachment_name,
                    "recipient": r.recipient,
                }
                for r in self.results
            ],
            "error": self.error,
        }


def get_job(job_id: str) -> Optional[BulkEmailDraftJob]:
    with _lock:
        return _jobs.get(job_id)


def is_bulk_running() -> bool:
    with _lock:
        return _running_job_id is not None


def reset_jobs_for_tests() -> None:
    """Clear in-memory job store (tests only)."""
    global _running_job_id
    with _lock:
        _jobs.clear()
        _running_job_id = None


def start_bulk_email_drafts(
    *,
    distributor_ids: List[int],
    reporting_quarter: str,
    actor: str,
) -> BulkEmailDraftJob:
    """
    Start a sequential bulk draft job in a background thread.

    Returns immediately with job_id for polling. Rejects if another bulk job
    is already running (duplicate protection).
    """
    ids = [int(i) for i in distributor_ids]
    if not ids:
        raise ValidationAppError("Select at least one distributor.")
    if len(ids) > _MAX_BATCH:
        raise ValidationAppError(f"Bulk draft creation is limited to {_MAX_BATCH} distributors.")

    # Preserve order, drop duplicates
    seen = set()
    ordered: List[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)

    quarter = normalize_reporting_month(reporting_quarter) or (reporting_quarter or "").strip()
    if not quarter:
        raise ValidationAppError("reporting_quarter is required (e.g. Q3 2026)")

    global _running_job_id
    with _lock:
        if _running_job_id is not None:
            raise ValidationAppError(
                "A bulk draft creation job is already running. Please wait for it to finish."
            )
        job_id = str(uuid.uuid4())
        job = BulkEmailDraftJob(
            job_id=job_id,
            status="queued",
            reporting_quarter=quarter,
            distributor_ids=ordered,
            actor=actor,
            total=len(ordered),
        )
        _jobs[job_id] = job
        _running_job_id = job_id

    thread = threading.Thread(
        target=_run_bulk_job,
        args=(job_id,),
        name=f"bulk-email-drafts-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return job


def _update_job(job_id: str, **kwargs: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = _utc_now()


def _append_result(job_id: str, item: BulkDraftItemResult) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.results.append(item)
        job.processed = len(job.results)
        if item.success:
            job.successful += 1
        else:
            job.failed += 1
        job.updated_at = _utc_now()


def _run_bulk_job(job_id: str) -> None:
    global _running_job_id
    job = get_job(job_id)
    if not job:
        return

    _update_job(job_id, status="running")
    logger.info(
        "Bulk email draft job started | job_id={} | count={} | quarter={}",
        job_id,
        job.total,
        job.reporting_quarter,
    )

    try:
        for distributor_id in list(job.distributor_ids):
            _process_one(job_id, distributor_id, job.reporting_quarter, job.actor)
        _update_job(job_id, status="completed")
        logger.info(
            "Bulk email draft job completed | job_id={} | successful={} | failed={}",
            job_id,
            get_job(job_id).successful if get_job(job_id) else "?",
            get_job(job_id).failed if get_job(job_id) else "?",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Bulk email draft job crashed | job_id={}", job_id)
        _update_job(job_id, status="failed", error="Bulk draft creation failed unexpectedly.")
    finally:
        with _lock:
            if _running_job_id == job_id:
                _running_job_id = None


def _process_one(
    job_id: str,
    distributor_id: int,
    reporting_quarter: str,
    actor: str,
) -> None:
    """Process one distributor with its own DB session (sequential, never parallel)."""
    db = SessionLocal()
    name = f"Distributor #{distributor_id}"
    try:
        from app.repositories.distributor_repository import DistributorRepository

        dist = DistributorRepository(db).get_by_id(distributor_id)
        if dist is not None:
            name = (dist.company or dist.name or name).strip()

        svc = TemplateGenerationService(db)
        result = svc.create_email_draft(
            distributor_id=distributor_id,
            reporting_quarter=reporting_quarter,
            actor=actor,
        )
        db.commit()
        _append_result(
            job_id,
            BulkDraftItemResult(
                distributor_id=distributor_id,
                distributor_name=result.distributor_name or name,
                success=True,
                draft_id=result.draft_id,
                attachment_name=result.attachment_name,
                recipient=result.recipient,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        reason = safe_failure_reason(exc)
        logger.warning(
            "Bulk draft item failed | job_id={} | distributor_id={} | reason={}",
            job_id,
            distributor_id,
            reason,
        )
        try:
            AuditService(db).log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.FAILED,
                    details=(
                        f"Distributor Email Draft Failed | distributor={name} | "
                        f"quarter={reporting_quarter} | reason={reason}"
                    ),
                    entity_type="distributor",
                    entity_id=str(distributor_id),
                    module="Distributor Communication",
                    status="Failure",
                    extra_metadata={
                        "reporting_quarter": reporting_quarter,
                        "failure_reason": reason,
                        "job_id": job_id,
                    },
                )
            )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to write audit for bulk draft failure")

        _append_result(
            job_id,
            BulkDraftItemResult(
                distributor_id=distributor_id,
                distributor_name=name,
                success=False,
                reason=reason,
            ),
        )
    finally:
        db.close()
