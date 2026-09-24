"""Remember which parser last succeeded for a distributor."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DistributorParserProfile(Base):
    """One saved parser strategy per distributor."""

    __tablename__ = "distributor_parser_profiles"
    __table_args__ = (
        UniqueConstraint("distributor_id", name="uq_distributor_parser_profiles_distributor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(
        ForeignKey("distributors.id", ondelete="CASCADE"),
        nullable=False,
    )
    parser_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    last_used: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
