"""User ↔ distributor permission mapping (many-to-many)."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.distributor import Distributor
    from app.models.user import User


class UserDistributor(Base, TimestampMixin):
    """Distributors a database user is authorized to access."""

    __tablename__ = "user_distributors"
    __table_args__ = (
        UniqueConstraint("user_id", "distributor_id", name="uq_user_distributors_user_distributor"),
        Index("ix_user_distributors_user_id", "user_id"),
        Index("ix_user_distributors_distributor_id", "distributor_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributor_id: Mapped[int] = mapped_column(
        ForeignKey("distributors.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="distributor_permissions",
    )
    distributor: Mapped["Distributor"] = relationship(
        "Distributor",
        foreign_keys=[distributor_id],
        back_populates="user_assignments",
    )

    def __repr__(self) -> str:
        return f"<UserDistributor user_id={self.user_id} distributor_id={self.distributor_id}>"
