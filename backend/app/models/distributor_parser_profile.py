"""Remember which parser last succeeded for a distributor."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DistributorParserProfile(Base):
    """One saved parser strategy for a distributor layout."""

    __tablename__ = "distributor_parser_profiles"
    __table_args__ = (
        UniqueConstraint(
            "distributor_id",
            "fingerprint_hash",
            name="uq_distributor_parser_profiles_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(
        ForeignKey("distributors.id", ondelete="CASCADE"),
        nullable=False,
    )
    parser_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    parser_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    layout_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    successful_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    last_used: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
