"""Product master ORM model."""

from typing import Optional

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, SoftDeleteMixin, TimestampMixin


class ProductMaster(Base, TimestampMixin, SoftDeleteMixin):
    """Product master data uploaded by Admin."""

    __tablename__ = "product_master"
    __table_args__ = (
        UniqueConstraint("product_code", name="uq_product_master_code"),
        Index("ix_product_master_name", "product_name"),
        Index("ix_product_master_segment", "segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="KG", server_default="KG", nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ProductMaster id={self.id} code={self.product_code!r}>"
