"""Email message / attachment repositories."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.email_message import EmailAttachment, EmailMessage
from app.repositories.base import BaseRepository


class EmailMessageRepository(BaseRepository[EmailMessage]):
    """Data access for Outlook email metadata."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, EmailMessage)

    def get_by_graph_id(self, graph_message_id: str) -> Optional[EmailMessage]:
        """Fetch email by Microsoft Graph message id."""
        query = (
            select(EmailMessage)
            .options(selectinload(EmailMessage.attachments))
            .where(
                EmailMessage.graph_message_id == graph_message_id,
                EmailMessage.is_deleted.is_(False),
            )
        )
        return self.db.scalar(query)

    def get_by_internet_message_id(self, internet_message_id: str) -> Optional[EmailMessage]:
        """Fetch email by RFC internet message id (cross-Graph-id dedupe)."""
        mid = (internet_message_id or "").strip()
        if not mid:
            return None
        query = (
            select(EmailMessage)
            .options(selectinload(EmailMessage.attachments))
            .where(
                EmailMessage.internet_message_id == mid,
                EmailMessage.is_deleted.is_(False),
            )
        )
        return self.db.scalar(query)

    def list_extracted(self, *, skip: int = 0, limit: int = 200) -> List[EmailMessage]:
        """List extracted emails newest first."""
        query = (
            select(EmailMessage)
            .options(selectinload(EmailMessage.attachments))
            .where(EmailMessage.is_deleted.is_(False))
            .order_by(EmailMessage.received_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(query).all())


class EmailAttachmentRepository(BaseRepository[EmailAttachment]):
    """Data access for email attachments."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, EmailAttachment)

    def get_by_graph_id(self, graph_attachment_id: str) -> Optional[EmailAttachment]:
        """Fetch attachment by Graph attachment id."""
        query = select(EmailAttachment).where(
            EmailAttachment.graph_attachment_id == graph_attachment_id,
            EmailAttachment.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def soft_delete_for_email(self, email_message_id: int) -> int:
        """Soft-delete all active attachments for an email. Returns count."""
        query = select(EmailAttachment).where(
            EmailAttachment.email_message_id == email_message_id,
            EmailAttachment.is_deleted.is_(False),
        )
        rows = list(self.db.scalars(query).all())
        for row in rows:
            self.soft_delete(row)
        return len(rows)
