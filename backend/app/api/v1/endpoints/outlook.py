"""Outlook sync and emails endpoints."""

from typing import List

from fastapi import APIRouter, Query

from app.dependencies.rbac import RequireAdmin, RequireUser
from app.dependencies.services import OutlookSyncServiceDep
from app.schemas.common import DataResponse
from app.schemas.email import (
    FrontendEmailRecord,
    OutlookOpenLinkResponse,
    OutlookSyncRequest,
    OutlookSyncResponse,
    SyncJobListResponse,
    SyncJobResponse,
)

router = APIRouter(tags=["Outlook Sync"])


@router.post(
    "/outlook/sync",
    response_model=OutlookSyncResponse,
    summary="Trigger Outlook mailbox sync",
    tags=["Outlook Sync"],
)
def trigger_outlook_sync(
    service: OutlookSyncServiceDep,
    current: RequireAdmin,
    payload: OutlookSyncRequest | None = None,
) -> OutlookSyncResponse:
    """
    Sync up to 5 unread Outlook emails per run, download Excel attachments,
    score accuracy, and mark messages as read on success (Admin).
    Click Sync again for the next batch of unread mail.
    """
    request = payload or OutlookSyncRequest()
    job = service.sync(request, actor=current.name)
    return OutlookSyncResponse(
        message=f"Outlook sync {job.status} (max {request.max_messages} unread)",
        job=SyncJobResponse.model_validate(job),
    )


@router.get(
    "/outlook/sync/jobs",
    response_model=SyncJobListResponse,
    summary="List sync jobs",
)
def list_sync_jobs(
    service: OutlookSyncServiceDep,
    _: RequireAdmin,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> SyncJobListResponse:
    """List Outlook sync jobs (Admin)."""
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
    _: RequireAdmin,
) -> DataResponse[SyncJobResponse]:
    """Get a sync job by id (Admin)."""
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
    _: RequireUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> List[FrontendEmailRecord]:
    """
    GET /api/emails — Emails work queue (not live Outlook inbox).

    Returns stored processing records that still need action.
    Already consolidated emails (``inserted`` / ``marked_read``) stay in the
    database but are omitted from this list.
    """
    messages = service.list_emails(skip=skip, limit=limit)
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
    _: RequireUser,
) -> OutlookOpenLinkResponse:
    """
    Return a navigable Outlook URL for the original message.

    Returns 404 with a clear message when the Graph message no longer exists.
    """
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
