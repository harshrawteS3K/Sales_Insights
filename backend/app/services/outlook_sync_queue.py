"""Outlook Sync Queue & Concurrency Control Manager."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.utils.datetime_utils import utc_now

logger = get_logger(__name__)


@dataclass
class SyncTaskItem:
    job_id: int
    user_id: Optional[int]
    user_email: Optional[str]
    user_name: str
    user_role: str
    mailbox: Optional[str]
    max_messages: int
    mark_as_read: bool
    sync_trigger: str = "manual"
    enqueued_at: datetime = field(default_factory=utc_now)


class OutlookSyncQueue:
    """
    Singleton thread-safe FIFO Queue ensuring only ONE Outlook sync runs at a time.

    Enforces race-condition prevention across multiple concurrent user sync requests.
    """

    _instance: Optional[OutlookSyncQueue] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> OutlookSyncQueue:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_queue()
            return cls._instance

    def _init_queue(self) -> None:
        self._task_queue: queue.Queue[SyncTaskItem] = queue.Queue()
        self._sync_lock = threading.Lock()
        self._active_task: Optional[SyncTaskItem] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._start_worker()

    def _start_worker(self) -> None:
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(
                target=self._worker_loop, name="OutlookSyncWorker", daemon=True
            )
            self._worker_thread.start()
            logger.info("OutlookSyncQueue background worker thread started")

    def enqueue(
        self,
        *,
        job_id: int,
        user_id: Optional[int],
        user_email: Optional[str],
        user_name: str,
        user_role: str,
        mailbox: Optional[str] = None,
        max_messages: int = 5,
        mark_as_read: bool = True,
        sync_trigger: str = "manual",
    ) -> SyncTaskItem:
        """Add a sync task to the FIFO queue."""
        task = SyncTaskItem(
            job_id=job_id,
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            user_role=user_role,
            mailbox=mailbox,
            max_messages=max_messages,
            mark_as_read=mark_as_read,
            sync_trigger=sync_trigger,
        )
        self._task_queue.put(task)
        logger.info(
            "Sync task enqueued | job_id={} | user_email={} | trigger={} | queue_size={}",
            job_id,
            user_email,
            sync_trigger,
            self._task_queue.qsize(),
        )
        self._start_worker()
        return task

    def get_status(self) -> Dict[str, Any]:
        """Return current status of the sync lock and queue."""
        active = self._active_task
        queued_list = list(self._task_queue.queue)
        return {
            "is_busy": active is not None,
            "active_job_id": active.job_id if active else None,
            "active_user_email": active.user_email if active else None,
            "active_user_name": active.user_name if active else None,
            "queue_length": len(queued_list),
            "queued_jobs": [
                {
                    "job_id": item.job_id,
                    "user_email": item.user_email,
                    "user_name": item.user_name,
                    "enqueued_at": item.enqueued_at.isoformat(),
                }
                for item in queued_list
            ],
        }

    def _worker_loop(self) -> None:
        """Continuous FIFO worker executing sync tasks one at a time."""
        while not self._shutdown_event.is_set():
            try:
                task = self._task_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            with self._sync_lock:
                self._active_task = task
                logger.info(
                    "Acquired global sync lock | job_id={} | user_email={}",
                    task.job_id,
                    task.user_email,
                )
                try:
                    self._execute_task(task)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Error executing queued sync task | job_id={} | error={}",
                        task.job_id,
                        exc,
                    )
                finally:
                    self._active_task = None
                    self._task_queue.task_done()
                    logger.info("Released global sync lock | job_id={}", task.job_id)

    def _execute_task(self, task: SyncTaskItem) -> None:
        """Run OutlookSyncService.sync_for_user in a dedicated DB session."""
        from app.database.session import SessionLocal
        from app.schemas.email import OutlookSyncRequest
        from app.services.outlook_sync_service import OutlookSyncService

        db = SessionLocal()
        try:
            service = OutlookSyncService(db)
            request = OutlookSyncRequest(
                mailbox=task.mailbox,
                max_messages=task.max_messages,
                mark_as_read=task.mark_as_read,
            )
            service.sync_for_user(
                job_id=task.job_id,
                user_id=task.user_id,
                user_email=task.user_email,
                user_role=task.user_role,
                request=request,
                actor=task.user_name,
                sync_trigger=task.sync_trigger,
            )
            # Worker sessions are NOT request-scoped — must commit or Graph mark-as-read
            # persists while extracted rows roll back on close (silent data loss).
            db.commit()
            logger.info("Sync task committed | job_id={}", task.job_id)
        except Exception:
            db.rollback()
            logger.exception("Sync task rolled back | job_id={}", task.job_id)
            raise
        finally:
            db.close()


def get_sync_queue() -> OutlookSyncQueue:
    """Return the global OutlookSyncQueue singleton."""
    return OutlookSyncQueue()
