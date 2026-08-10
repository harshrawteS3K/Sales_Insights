"""Distributor ↔ customer mapping learned from quarterly imports."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.distributor import Distributor
    from app.models.report import Report


class DistributorCustomerMapping(Base, TimestampMixin):
    """Customers previously submitted by a distributor (learned on import)."""

    __tablename__ = "distributor_customer_mappings"
    __table_args__ = (
        UniqueConstraint(
            "distributor_id",
            "customer_name",
            name="uq_distributor_customer_mappings_dist_customer",
        ),
        Index("ix_distributor_customer_mappings_distributor_id", "distributor_id"),
        Index(
            "ix_distributor_customer_mappings_active",
            "distributor_id",
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("distributors.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_report_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    first_seen_quarter: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    distributor: Mapped["Distributor"] = relationship(
        "Distributor",
        back_populates="customer_mappings",
    )
    source_report: Mapped[Optional["Report"]] = relationship("Report")

    def __repr__(self) -> str:
        return (
            f"<DistributorCustomerMapping id={self.id} "
            f"distributor_id={self.distributor_id} customer={self.customer_name!r}>"
        )
