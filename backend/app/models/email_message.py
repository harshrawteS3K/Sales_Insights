"""Email message and attachment ORM models for Outlook sync metadata."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin
from app.enums import EmailProcessStatus

if TYPE_CHECKING:
    from app.models.report import Report


class EmailMessage(Base, TimestampMixin, SoftDeleteMixin):
    """Outlook email metadata captured during Graph sync."""

    __tablename__ = "email_messages"
    __table_args__ = (
        Index(
            "uq_email_messages_graph_id_active",
            "graph_message_id",
            unique=True,
            postgresql_where="is_deleted = false",
        ),
        Index(
            "uq_email_messages_internet_id_active",
            "internet_message_id",
            unique=True,
            postgresql_where="is_deleted = false AND internet_message_id IS NOT NULL",
        ),
        Index("ix_email_messages_sender_email", "sender_email"),
        Index("ix_email_messages_received_at", "received_at"),
        Index("ix_email_messages_process_status", "process_status"),
        Index("ix_email_messages_is_read", "is_read"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    graph_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    internet_message_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subject: Mapped[str] = mapped_column(String(1000), nullable=False)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    body_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_attachments: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    process_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=EmailProcessStatus.UNREAD.value,
        server_default=EmailProcessStatus.UNREAD.value,
    )
    confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mailbox: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    outlook_web_link: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    parsed_distributor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parsed_location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    parsed_segment: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    detected_quarter: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    parsed_unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    subject_valid: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    # python | llm | manual — how Excel columns were mapped during extraction/scoring
    mapping_source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    attachments: Mapped[List["EmailAttachment"]] = relationship(
        "EmailAttachment",
        back_populates="email_message",
        cascade="all, delete-orphan",
    )
    reports: Mapped[List["Report"]] = relationship(
        "Report",
        back_populates="email_message",
    )

    def __repr__(self) -> str:
        return f"<EmailMessage id={self.id} subject={self.subject!r}>"


class EmailAttachment(Base, TimestampMixin, SoftDeleteMixin):
    """Excel attachment downloaded from an Outlook email."""

    __tablename__ = "email_attachments"
    __table_args__ = (
        Index(
            "uq_email_attachments_graph_id_active",
            "graph_attachment_id",
            unique=True,
            postgresql_where="is_deleted = false",
        ),
        Index("ix_email_attachments_email_message_id", "email_message_id"),
        Index("ix_email_attachments_file_name", "file_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    graph_attachment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_excel: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    email_message_id: Mapped[int] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"),
        nullable=False,
    )

    email_message: Mapped["EmailMessage"] = relationship(
        "EmailMessage",
        back_populates="attachments",
    )

    def __repr__(self) -> str:
        return f"<EmailAttachment id={self.id} file_name={self.file_name!r}>"
