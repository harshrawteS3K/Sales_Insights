"""Lookup and store distributor parser profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.distributor_parser_profile import DistributorParserProfile


class ParserProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_distributor(self, distributor_id: int) -> Optional[DistributorParserProfile]:
        stmt = select(DistributorParserProfile).where(
            DistributorParserProfile.distributor_id == distributor_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        distributor_id: int,
        parser_strategy: str,
        confidence: float,
    ) -> DistributorParserProfile:
        now = datetime.now(timezone.utc)
        row = self.get_by_distributor(distributor_id)
        if row is None:
            row = DistributorParserProfile(
                distributor_id=distributor_id,
                parser_strategy=parser_strategy,
                confidence=float(confidence),
                last_used=now,
                created_at=now,
            )
            self.db.add(row)
        else:
            row.parser_strategy = parser_strategy
            row.confidence = float(confidence)
            row.last_used = now
        self.db.flush()
        return row
