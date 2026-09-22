"""User ↔ segment permission mapping (many-to-many)."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserSegment(Base, TimestampMixin):
    """Segments a database user may access (Segment Head / persona).

    ``active=True`` → current live access (matrix checkbox ticked).
    ``active=False, retain_history=True`` → no new access; historical data still visible.
    ``active=False, retain_history=False`` → segment fully removed from visibility.
    """

    __tablename__ = "user_segments"
    __table_args__ = (
        UniqueConstraint("user_id", "segment", name="uq_user_segments_user_segment"),
        Index("ix_user_segments_user_id", "user_id"),
        Index("ix_user_segments_segment", "segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment: Mapped[str] = mapped_column(String(150), nullable=False)
    assigned_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    retain_history: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    user: Mapped["User"] = relationship("User", back_populates="segment_permissions", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return (
            f"<UserSegment user_id={self.user_id} segment={self.segment!r} "
            f"active={self.active} retain_history={self.retain_history}>"
        )
