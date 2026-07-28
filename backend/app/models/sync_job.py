"""Outlook sync job ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin
from app.enums import SyncStatus


class SyncJob(Base, TimestampMixin):
    """Tracks a Microsoft Graph mailbox sync run."""

    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("ix_sync_jobs_status", "status"),
        Index("ix_sync_jobs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SyncStatus.STARTED.value,
        server_default=SyncStatus.STARTED.value,
    )
    mailbox: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    emails_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    emails_processed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    attachments_downloaded: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    reports_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<SyncJob id={self.id} status={self.status!r}>"
