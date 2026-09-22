"""User ORM model."""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin
from app.enums import OutlookSyncPermission, UserRole

if TYPE_CHECKING:
    from app.models.audit_trail import AuditTrail
    from app.models.report import Report
    from app.models.user_distributor import UserDistributor
    from app.models.user_segment import UserSegment


class User(Base, TimestampMixin, SoftDeleteMixin):
    """Application user with RBAC role and hashed credentials."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email_active", "email", unique=True, postgresql_where="is_deleted = false"),
        Index(
            "ix_users_username_active",
            "username",
            unique=True,
            postgresql_where="is_deleted = false",
        ),
        Index("ix_users_role", "role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=UserRole.USER.value,
        server_default=UserRole.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outlook_sync_permission: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OutlookSyncPermission.OWN.value,
        server_default=OutlookSyncPermission.OWN.value,
    )

    reports: Mapped[List["Report"]] = relationship(
        "Report",
        back_populates="uploaded_by_user",
        foreign_keys="Report.uploaded_by",
    )
    audit_logs: Mapped[List["AuditTrail"]] = relationship(
        "AuditTrail",
        back_populates="user",
        foreign_keys="AuditTrail.user_id",
    )
    distributor_permissions: Mapped[List["UserDistributor"]] = relationship(
        "UserDistributor",
        foreign_keys="[UserDistributor.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    segment_permissions: Mapped[List["UserSegment"]] = relationship(
        "UserSegment",
        foreign_keys="[UserSegment.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
