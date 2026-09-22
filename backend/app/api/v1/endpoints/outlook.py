"""Outlook sync and emails endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.rbac import (
    RequireAdmin,
    RequireUser,
    distributor_companies_scope_for_user,
    segment_scope_for_user,
)
from app.dependencies.services import OutlookSyncServiceDep
from app.enums import OutlookSyncPermission, SyncStatus, UserRole
from app.exceptions import ForbiddenError, ValidationAppError
from app.models.sync_job import SyncJob
from app.schemas.common import DataResponse
from app.schemas.email import (
    FrontendEmailRecord,
    OutlookAutoSyncStatusResponse,
    OutlookOpenLinkResponse,
    OutlookSyncRequest,
    OutlookSyncResponse,
    SyncJobListResponse,
    SyncJobResponse,
)
from app.services.outlook_auto_sync_scheduler import get_outlook_auto_sync_status
from app.services.outlook_sync_queue import get_sync_queue
from app.utils.datetime_utils import utc_now

router = APIRouter(tags=["Outlook Sync"])


def _resolve_user_email(current: RequireUser, db: Session) -> Optional[str]:
    """Prefer RBAC header email, then DB user.email."""
    email = (current.email or "").strip() or None
    if email:
        return email
    if current.user_id:
        from app.repositories.user_repository import UserRepository

        row = UserRepository(db).get_by_id(current.user_id)
        if row and (row.email or "").strip():
            return row.email.strip()
    return None


def _resolve_outlook_sync_permission(current: RequireUser, db: Session) -> str:
    """Resolve Sync Outlook permission (none | own | all)."""
    role_val = current.role.value if hasattr(current.role, "value") else str(current.role)
    if role_val == UserRole.SUPER_ADMIN.value:
        return OutlookSyncPermission.ALL.value
    if current.user_id:
        from app.repositories.user_repository import UserRepository

        row = UserRepository(db).get_by_id(current.user_id)
        if row is not None:
            perm = (getattr(row, "outlook_sync_permission", None) or "").strip().lower()
            if perm in {
                OutlookSyncPermission.NONE.value,
                OutlookSyncPermission.OWN.value,
                OutlookSyncPermission.ALL.value,
            }:
                return perm
            if row.role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
                return OutlookSyncPermission.ALL.value
            return OutlookSyncPermission.OWN.value
    if role_val in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
        return OutlookSyncPermission.ALL.value
    return OutlookSyncPermission.OWN.value


@router.post(
    "/outlook/sync",
    response_model=OutlookSyncResponse,
    summary="Trigger Outlook mailbox sync",
    tags=["Outlook Sync"],
)
def trigger_outlook_sync(
    service: OutlookSyncServiceDep,
    current: RequireUser,
    db: Session = Depends(get_db),
    payload: OutlookSyncRequest | None = None,
) -> OutlookSyncResponse:
    """
    Enqueue Outlook sync for the logged-in user.

    Permission drives sender scope:
    - own → FROM == logged-in user email
    - all → full shared mailbox (same as scheduler)
    - none → forbidden
    """
    request = payload or OutlookSyncRequest()
    mailbox = service.graph.resolve_mailbox(request.mailbox)
    role_val = current.role.value if hasattr(current.role, "value") else str(current.role)
    perm = _resolve_outlook_sync_permission(current, db)

    if perm == OutlookSyncPermission.NONE.value:
        raise ForbiddenError("Outlook sync is disabled for your account.")

    user_email = _resolve_user_email(current, db)
    if perm == OutlookSyncPermission.OWN.value:
        if not user_email or "@" not in user_email:
            raise ValidationAppError(
                "Your account has no email address. Ask Admin to set your email in "
                "Persona Management, then Sync Outlook again."
            )
        sync_sender = user_email
    else:
        sync_sender = None

    job = SyncJob(
        status=SyncStatus.STARTED.value,
        mailbox=mailbox,
        started_at=utc_now(),
        triggered_by=current.name,
        details={
            "mark_as_read": request.mark_as_read,
            "max_messages": request.max_messages,
            "user_email": user_email,
            "sender_filter": sync_sender,
            "sync_trigger": "manual",
            "outlook_sync_permission": perm,
        },
    )
    job = service.sync_jobs.create(job)
    db.commit()
    db.refresh(job)

    get_sync_queue().enqueue(
        job_id=job.id,
        user_id=current.user_id,
        user_email=sync_sender,
        user_name=current.name,
        user_role=role_val,
        mailbox=mailbox,
        max_messages=request.max_messages,
        mark_as_read=request.mark_as_read,
        sync_trigger="manual",
    )

    if sync_sender:
        msg = (
            f"Outlook sync started for {sync_sender} (job #{job.id}). "
            f"Checking for unread Excel emails FROM that address…"
        )
    else:
        msg = f"Outlook sync started for full mailbox (job #{job.id})"

    return OutlookSyncResponse(
        message=msg,
        job=SyncJobResponse.model_validate(job),
    )


@router.get(
    "/outlook/sync/status",
    response_model=DataResponse[OutlookAutoSyncStatusResponse],
    summary="Auto Outlook sync scheduler status",
    tags=["Outlook Sync"],
)
def get_outlook_auto_sync_status_endpoint(
    current: RequireUser,
    db: Session = Depends(get_db),
) -> DataResponse[OutlookAutoSyncStatusResponse]:
    """Return APScheduler auto-sync status for the Emails status card."""
    perm = _resolve_outlook_sync_permission(current, db)
    if perm == OutlookSyncPermission.NONE.value:
        raise ForbiddenError("Emails module is disabled for your account.")
    status = get_outlook_auto_sync_status()
    return DataResponse(data=OutlookAutoSyncStatusResponse(**status))


@router.get(
    "/outlook/sync/queue",
    summary="Get Outlook Sync FIFO Queue status",
    tags=["Outlook Sync"],
)
def get_outlook_sync_queue_status(
    _: RequireUser,
) -> DataResponse[dict]:
    """Get status of the global Outlook sync lock and pending FIFO queue."""
    status = get_sync_queue().get_status()
    return DataResponse(data=status)


@router.get(
    "/outlook/sync/jobs",
    response_model=SyncJobListResponse,
    summary="List sync jobs",
)
def list_sync_jobs(
    service: OutlookSyncServiceDep,
    _: RequireUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> SyncJobListResponse:
    """List Outlook sync jobs."""
    jobs = service.list_sync_jobs(skip=skip, limit=limit)
    return SyncJobListResponse(
        data=[SyncJobResponse.model_validate(j) for j in jobs],
        total=service.count_sync_jobs(),
    )


@router.get(
    "/outlook/sync/jobs/{job_id}",
    response_model=DataResponse[SyncJobResponse],
    summary="Get sync job",
)
def get_sync_job(
    job_id: int,
    service: OutlookSyncServiceDep,
    _: RequireUser,
) -> DataResponse[SyncJobResponse]:
    """Get a sync job by id."""
    job = service.get_sync_job(job_id)
    return DataResponse(data=SyncJobResponse.model_validate(job))


@router.get(
    "/emails",
    response_model=List[FrontendEmailRecord],
    summary="List email processing history",
    tags=["Emails"],
)
def list_emails(
    service: OutlookSyncServiceDep,
    current: RequireUser,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> List[FrontendEmailRecord]:
    """
    GET /api/emails — Emails work queue (not live Outlook inbox).

    Sync Own: only emails where ``sender_email`` matches persona email.
    Sync All: full queue (still subject to access-mode filters when set).
    """
    perm = _resolve_outlook_sync_permission(current, db)
    if perm == OutlookSyncPermission.NONE.value:
        raise ForbiddenError("Emails module is disabled for your account.")

    sender_email: Optional[str] = None
    if perm == OutlookSyncPermission.OWN.value:
        sender_email = _resolve_user_email(current, db)
        if not sender_email:
            return []

    allowed = segment_scope_for_user(current, db)
    companies = distributor_companies_scope_for_user(current, db)

    messages = service.list_emails(
        skip=skip,
        limit=limit,
        allowed_segments=allowed,
        allowed_companies=companies,
        sender_email=sender_email,
    )
    return service.to_frontend_emails(messages)


@router.get(
    "/emails/{email_id}/outlook-link",
    response_model=OutlookOpenLinkResponse,
    summary="Resolve Outlook web URL for a processing history email",
    tags=["Emails"],
)
def get_outlook_open_link(
    email_id: int,
    service: OutlookSyncServiceDep,
    current: RequireUser,
    db: Session = Depends(get_db),
) -> OutlookOpenLinkResponse:
    """Return a navigable Outlook URL for the original message."""
    perm = _resolve_outlook_sync_permission(current, db)
    if perm == OutlookSyncPermission.NONE.value:
        raise ForbiddenError("Emails module is disabled for your account.")
    result = service.resolve_outlook_open_link(email_id)
    return OutlookOpenLinkResponse(**result)


@router.delete(
    "/emails/{email_id}",
    response_model=DataResponse[dict],
    summary="Delete email processing history record",
    tags=["Emails"],
)
def delete_email_record(
    email_id: int,
    service: OutlookSyncServiceDep,
    current: RequireAdmin,
) -> DataResponse[dict]:
    """
    Soft-delete an email processing history record from Sales Insights.

    Does not delete the original message from Outlook.
    """
    result = service.delete_email_record(email_id, actor=current.name)
    return DataResponse(data=result, message=result.get("message", "Deleted"))
