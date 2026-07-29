"""Product master ORM model."""

from typing import Optional

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, SoftDeleteMixin, TimestampMixin


class ProductMaster(Base, TimestampMixin, SoftDeleteMixin):
    """Product master data uploaded by Admin (Phase 2: industry_type + product_code)."""

    __tablename__ = "product_master"
    __table_args__ = (
        Index("ix_product_master_name", "product_name"),
        Index("ix_product_master_segment", "segment"),
        Index("ix_product_master_industry_type", "industry_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    industry_type: Mapped[str] = mapped_column(String(255), nullable=False)
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    # Legacy optional fields retained for backward compatibility
    product_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    segment: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="KG", server_default="KG", nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ProductMaster id={self.id} code={self.product_code!r} industry={self.industry_type!r}>"
