"""Sales record ORM model."""

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.distributor import Distributor
    from app.models.report import Report


class SalesRecord(Base, TimestampMixin, SoftDeleteMixin):
    """Individual sales line extracted from a distributor report."""

    __tablename__ = "sales_records"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "row_hash",
            name="uq_sales_records_report_row_hash",
        ),
        Index("ix_sales_records_distributor_id", "distributor_id"),
        Index("ix_sales_records_report_id", "report_id"),
        Index("ix_sales_records_customer_name", "customer_name"),
        Index("ix_sales_records_product", "product"),
        Index("ix_sales_records_segment", "segment"),
        Index("ix_sales_records_period", "period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sr_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str] = mapped_column(String(150), nullable=False)
    product: Mapped[str] = mapped_column(String(150), nullable=False)
    opening_stock: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
    closing_stock: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    quantity_display: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Legacy / denormalized copy of report.reporting_month (nullable for new template)
    period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="KG", server_default="KG", nullable=False)
    row_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("distributors.id", ondelete="SET NULL"),
        nullable=True,
    )

    report: Mapped["Report"] = relationship("Report", back_populates="sales_records")
    distributor: Mapped[Optional["Distributor"]] = relationship(
        "Distributor",
        back_populates="sales_records",
    )

    def __repr__(self) -> str:
        return (
            f"<SalesRecord id={self.id} customer={self.customer_name!r} "
            f"product={self.product!r} qty={self.quantity}>"
        )
