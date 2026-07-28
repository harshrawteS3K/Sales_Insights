"""Audit trail ORM model."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.enums import AuditAction

if TYPE_CHECKING:
    from app.models.user import User


class AuditTrail(Base, TimestampMixin):
    """Immutable audit log entry for system actions."""

    __tablename__ = "audit_trail"
    __table_args__ = (
        Index("ix_audit_trail_action", "action"),
        Index("ix_audit_trail_user_id", "user_id"),
        Index("ix_audit_trail_entity_type", "entity_type"),
        Index("ix_audit_trail_created_at", "created_at"),
        Index("ix_audit_trail_report_name", "report_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=AuditAction.VIEWED.value,
    )
    details: Mapped[str] = mapped_column(Text, nullable=False)
    report_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="audit_logs",
        foreign_keys=[user_id],
    )

    def __repr__(self) -> str:
        return f"<AuditTrail id={self.id} action={self.action!r} user={self.user_name!r}>"
