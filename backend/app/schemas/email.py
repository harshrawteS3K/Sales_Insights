"""Email and Outlook sync schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import TimestampSchema


class EmailAttachmentResponse(TimestampSchema):
    """Email attachment metadata."""

    id: int
    graph_attachment_id: str
    file_name: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    file_path: Optional[str] = None
    content_hash: Optional[str] = None
    is_excel: bool = True
    email_message_id: int


class EmailMessageResponse(TimestampSchema):
    """Email message metadata."""

    id: int
    graph_message_id: str
    subject: str
    sender_name: Optional[str] = None
    sender_email: str
    received_at: datetime
    body_preview: Optional[str] = None
    has_attachments: bool
    is_read: bool
    process_status: str
    confidence_score: Optional[int] = None
    error_message: Optional[str] = None
    mailbox: Optional[str] = None
    attachments: List[EmailAttachmentResponse] = Field(default_factory=list)


class FrontendEmailRecord(BaseModel):
    """Frontend EmailsModule shape: GET /api/emails."""

    id: int
    senderName: str
    senderEmail: str
    subject: str
    dateReceived: str
    confidenceScore: int
    outlookWebLink: Optional[str] = None
    graphMessageId: Optional[str] = None
    mailbox: Optional[str] = None
    processStatus: str = "unread"
    statusLabel: str = "New"
    attachmentName: Optional[str] = None
    distributorName: Optional[str] = None
    distributor: Optional[str] = None
    location: Optional[str] = None
    segment: Optional[str] = None
    quarter: Optional[str] = None
    subjectValid: bool = False
    hasExcel: bool = False
    errorMessage: Optional[str] = None
    mappingSource: Optional[str] = None  # python | llm | manual


class OutlookOpenLinkResponse(BaseModel):
    """Resolved Outlook web URL for the View button."""

    success: bool = True
    url: str
    available: bool = True
    message: Optional[str] = None


class SyncJobResponse(TimestampSchema):
    """Outlook sync job response."""

    id: int
    status: str
    mailbox: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    emails_found: int
    emails_processed: int
    attachments_downloaded: int
    reports_created: int
    records_inserted: int
    duplicates_skipped: int
    failures: int
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    triggered_by: Optional[str] = None


class OutlookSyncRequest(BaseModel):
    """Optional sync request body."""

    mailbox: Optional[str] = None
    mark_as_read: bool = True
    # Cap per sync run (Emails work-queue batch size). Graph pages until this limit.
    # Manual UI typically uses 5; automated scheduler may use a higher batch.
    max_messages: int = Field(default=5, ge=1, le=100)


class OutlookAutoSyncStatusResponse(BaseModel):
    """Auto-sync scheduler status for the Emails UI card."""

    status: str
    frequency: str
    last_successful_sync: Optional[str] = None
    next_scheduled_sync: Optional[str] = None


class OutlookSyncResponse(BaseModel):
    """Sync trigger response."""

    success: bool = True
    message: str
    job: SyncJobResponse


class SyncJobListResponse(BaseModel):
    """List of Outlook sync jobs (backend contract)."""

    success: bool = True
    data: List[SyncJobResponse]
    total: int
