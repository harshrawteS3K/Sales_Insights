"""APScheduler-backed automatic Outlook synchronization (every 30 minutes)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import get_logger
from app.enums import SyncStatus
from app.utils.datetime_utils import utc_now

logger = get_logger(__name__)

_SCHEDULER_JOB_ID = "outlook_auto_sync"
_SETTING_LAST_SUCCESS = "outlook_auto_sync_last_success"

_scheduler: Optional[BackgroundScheduler] = None
_last_success_at: Optional[datetime] = None


def _load_last_success_from_db() -> Optional[datetime]:
    try:
        from sqlalchemy import select

        from app.database.session import SessionLocal
        from app.models.system_setting import SystemSetting

        db = SessionLocal()
        try:
            row = db.scalar(
                select(SystemSetting).where(SystemSetting.key == _SETTING_LAST_SUCCESS)
            )
            if not row or not (row.value or "").strip():
                return None
            return datetime.fromisoformat(row.value.strip())
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("Failed loading outlook auto-sync last success")
        return None


def record_auto_sync_success(when: Optional[datetime] = None) -> None:
    """Persist last successful automated sync timestamp."""
    global _last_success_at
    stamp = when or utc_now()
    _last_success_at = stamp
    try:
        from sqlalchemy import select

        from app.database.session import SessionLocal
        from app.models.system_setting import SystemSetting

        db = SessionLocal()
        try:
            row = db.scalar(
                select(SystemSetting).where(SystemSetting.key == _SETTING_LAST_SUCCESS)
            )
            iso = stamp.isoformat()
            if row:
                row.value = iso
            else:
                db.add(SystemSetting(key=_SETTING_LAST_SUCCESS, value=iso))
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("Failed persisting outlook auto-sync last success")


def _run_automated_outlook_sync() -> None:
    """Enqueue a full-mailbox Outlook sync as System (reuses existing sync service)."""
    from app.database.session import SessionLocal
    from app.models.sync_job import SyncJob
    from app.services.outlook_sync_queue import get_sync_queue
    from app.services.outlook_sync_service import OutlookSyncService

    db = SessionLocal()
    try:
        service = OutlookSyncService(db)
        mailbox = service.graph.resolve_mailbox(None)
        job = SyncJob(
            status=SyncStatus.STARTED.value,
            mailbox=mailbox,
            started_at=utc_now(),
            triggered_by="System",
            details={
                "trigger": "automated",
                "mark_as_read": True,
                "max_messages": 50,
                "sender_filter": None,
            },
        )
        job = service.sync_jobs.create(job)
        db.commit()
        db.refresh(job)

        get_sync_queue().enqueue(
            job_id=job.id,
            user_id=None,
            user_email=None,
            user_name="System",
            user_role="system",
            mailbox=mailbox,
            max_messages=50,
            mark_as_read=True,
            sync_trigger="automated",
        )
        logger.info("Automated Outlook Sync enqueued | job_id={}", job.id)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Automated Outlook Sync failed to enqueue")
    finally:
        db.close()


def start_outlook_auto_sync_scheduler() -> None:
    """Start BackgroundScheduler on FastAPI startup."""
    global _scheduler, _last_success_at
    if _scheduler is not None and _scheduler.running:
        return

    _last_success_at = _load_last_success_from_db()
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run_automated_outlook_sync,
        trigger=IntervalTrigger(minutes=30),
        id=_SCHEDULER_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("APScheduler Outlook auto-sync started | interval=30m")


def stop_outlook_auto_sync_scheduler() -> None:
    """Shut down scheduler on FastAPI shutdown."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
    except Exception:  # noqa: BLE001
        logger.exception("Error shutting down Outlook auto-sync scheduler")
    finally:
        _scheduler = None
        logger.info("APScheduler Outlook auto-sync stopped")


def get_outlook_auto_sync_status() -> Dict[str, Any]:
    """Status payload for Emails UI auto-sync card."""
    global _last_success_at
    if _last_success_at is None:
        _last_success_at = _load_last_success_from_db()

    next_run: Optional[datetime] = None
    running = False
    if _scheduler is not None and _scheduler.running:
        running = True
        job = _scheduler.get_job(_SCHEDULER_JOB_ID)
        if job is not None and job.next_run_time is not None:
            next_run = job.next_run_time

    return {
        "status": "Running" if running else "Stopped",
        "frequency": "Every 30 Minutes",
        "last_successful_sync": _last_success_at.isoformat() if _last_success_at else None,
        "next_scheduled_sync": next_run.isoformat() if next_run else None,
    }
