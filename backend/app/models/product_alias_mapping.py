"""Distributor product name → normalized product name (mapping history)."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.distributor import Distributor


class ProductAliasMapping(Base, TimestampMixin):
    """
    One source product name as a distributor sent it, and its normalized name.

    ``distributor_id`` NULL is a global mapping. A distributor-specific row wins
    over a global row for the same original name. Sales records keep their
    original product text; this table never rewrites them.
    """

    __tablename__ = "product_alias_mappings"
    __table_args__ = (
        Index(
            "uq_product_alias_mappings_dist_original_active",
            "distributor_id",
            text("lower(original_product_name)"),
            unique=True,
            postgresql_where=text("is_active = true AND distributor_id IS NOT NULL"),
        ),
        Index(
            "uq_product_alias_mappings_global_original_active",
            text("lower(original_product_name)"),
            unique=True,
            postgresql_where=text("is_active = true AND distributor_id IS NULL"),
        ),
        Index("ix_product_alias_mappings_distributor_id", "distributor_id"),
        Index("ix_product_alias_mappings_normalized", "normalized_product_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    distributor_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("distributors.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    distributor: Mapped[Optional["Distributor"]] = relationship("Distributor")

    def __repr__(self) -> str:
        return (
            f"<ProductAliasMapping id={self.id} distributor_id={self.distributor_id} "
            f"original={self.original_product_name!r} normalized={self.normalized_product_name!r}>"
        )
