"""Distributor ORM model."""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.distributor_customer_mapping import DistributorCustomerMapping
    from app.models.report import Report
    from app.models.sales_record import SalesRecord


class Distributor(Base, TimestampMixin, SoftDeleteMixin):
    """Distributor / sales partner master record."""

    __tablename__ = "distributors"
    __table_args__ = (
        Index("ix_distributors_name", "name"),
        Index("ix_distributors_email", "email"),
        Index("ix_distributors_company", "company"),
        Index(
            "uq_distributors_company_active",
            text("lower(trim(company))"),
            unique=True,
            postgresql_where=text(
                "is_deleted = false AND company IS NOT NULL AND TRIM(company) <> ''"
            ),
        ),
        Index(
            "ix_distributors_email_active",
            "email",
            unique=True,
            postgresql_where="is_deleted = false AND email IS NOT NULL",
        ),
        Index(
            "uq_distributors_code_active",
            "code",
            unique=True,
            postgresql_where=text(
                "is_deleted = false AND code IS NOT NULL AND TRIM(code) <> ''"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cc_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pincode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reports: Mapped[List["Report"]] = relationship("Report", back_populates="distributor")
    sales_records: Mapped[List["SalesRecord"]] = relationship(
        "SalesRecord",
        back_populates="distributor",
    )
    customer_mappings: Mapped[List["DistributorCustomerMapping"]] = relationship(
        "DistributorCustomerMapping",
        back_populates="distributor",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Distributor id={self.id} name={self.name!r}>"
