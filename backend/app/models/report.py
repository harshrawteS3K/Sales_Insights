"""Report ORM model for sales / market research reports."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin
from app.enums import ReportSource, ReportStatus

if TYPE_CHECKING:
    from app.models.distributor import Distributor
    from app.models.email_message import EmailMessage
    from app.models.sales_record import SalesRecord
    from app.models.user import User


class Report(Base, TimestampMixin, SoftDeleteMixin):
    """Sales or market research report metadata."""

    __tablename__ = "reports"
    __table_args__ = (
        Index(
            "uq_reports_content_hash_active",
            "content_hash",
            unique=True,
            postgresql_where="is_deleted = false AND content_hash IS NOT NULL",
        ),
        Index(
            "uq_reports_distributor_month_active",
            "distributor_id",
            "reporting_month",
            unique=True,
            postgresql_where=(
                "is_deleted = false AND distributor_id IS NOT NULL "
                "AND reporting_month IS NOT NULL AND TRIM(reporting_month) <> ''"
            ),
        ),
        Index("ix_reports_status", "status"),
        Index("ix_reports_source", "source"),
        Index("ix_reports_reporting_month", "reporting_month"),
        Index("ix_reports_distributor_id", "distributor_id"),
        Index("ix_reports_report_date", "report_date"),
        Index("ix_reports_type", "report_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        default=lambda: str(uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Sales Report",
        server_default="Sales Report",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ReportStatus.PENDING.value,
        server_default=ReportStatus.PENDING.value,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ReportSource.UPLOAD.value,
        server_default=ReportSource.UPLOAD.value,
    )
    reporting_month: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    report_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    categories: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    distributor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("distributors.id", ondelete="SET NULL"),
        nullable=True,
    )
    email_message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("email_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Denormalized sender metadata (survives email history soft-delete)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    graph_message_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    internet_message_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mailbox: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    distributor: Mapped[Optional["Distributor"]] = relationship(
        "Distributor",
        back_populates="reports",
    )
    email_message: Mapped[Optional["EmailMessage"]] = relationship(
        "EmailMessage",
        back_populates="reports",
    )
    uploaded_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="reports",
        foreign_keys=[uploaded_by],
    )
    sales_records: Mapped[List["SalesRecord"]] = relationship(
        "SalesRecord",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Report id={self.id} name={self.name!r} status={self.status!r}>"
