"""Customer master ORM model."""

from typing import Optional

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, SoftDeleteMixin, TimestampMixin


class CustomerMaster(Base, TimestampMixin, SoftDeleteMixin):
    """Customer master data uploaded by Admin."""

    __tablename__ = "customer_master"
    __table_args__ = (
        UniqueConstraint("customer_code", name="uq_customer_master_code"),
        Index("ix_customer_master_name", "customer_name"),
        Index("ix_customer_master_segment", "segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_code: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str] = mapped_column(String(150), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CustomerMaster id={self.id} code={self.customer_code!r}>"
