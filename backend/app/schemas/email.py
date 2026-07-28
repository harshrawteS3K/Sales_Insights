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
    max_messages: int = Field(default=50, ge=1, le=200)


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
