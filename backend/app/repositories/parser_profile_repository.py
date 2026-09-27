"""Lookup and store distributor parser profiles.

A distributor may keep one profile per fingerprint. A new layout is inserted.
An existing fingerprint is updated in place.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.distributor_parser_profile import DistributorParserProfile


class ParserProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_distributor(self, distributor_id: int) -> List[DistributorParserProfile]:
        stmt = (
            select(DistributorParserProfile)
            .where(DistributorParserProfile.distributor_id == distributor_id)
            .order_by(DistributorParserProfile.last_used.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_distributor(self, distributor_id: int) -> Optional[DistributorParserProfile]:
        """Most recently used profile. Kept for callers that expect one row."""
        rows = self.list_for_distributor(distributor_id)
        return rows[0] if rows else None

    def get_by_fingerprint(
        self,
        distributor_id: int,
        fingerprint_hash: Optional[str],
    ) -> Optional[DistributorParserProfile]:
        fingerprint = (fingerprint_hash or "").strip().upper() or None
        stmt = select(DistributorParserProfile).where(
            DistributorParserProfile.distributor_id == distributor_id
        )
        if fingerprint:
            stmt = stmt.where(DistributorParserProfile.fingerprint_hash == fingerprint)
        else:
            stmt = stmt.where(DistributorParserProfile.fingerprint_hash.is_(None))
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        distributor_id: int,
        parser_strategy: str,
        confidence: float,
        *,
        parser_name: Optional[str] = None,
        parser_version: Optional[str] = None,
        layout_type: Optional[str] = None,
        fingerprint_hash: Optional[str] = None,
    ) -> DistributorParserProfile:
        now = datetime.now(timezone.utc)
        fingerprint = (fingerprint_hash or "").strip().upper() or None
        row = self.get_by_fingerprint(distributor_id, fingerprint)
        if row is None:
            row = DistributorParserProfile(
                distributor_id=distributor_id,
                parser_strategy=parser_strategy,
                parser_name=parser_name or parser_strategy,
                parser_version=parser_version,
                layout_type=layout_type,
                fingerprint_hash=fingerprint,
                successful_runs=1,
                confidence=float(confidence),
                last_used=now,
                created_at=now,
            )
            self.db.add(row)
        else:
            row.parser_strategy = parser_strategy
            row.parser_name = parser_name or parser_strategy
            if parser_version:
                row.parser_version = parser_version
            if layout_type:
                row.layout_type = layout_type
            if fingerprint:
                row.fingerprint_hash = fingerprint
            row.successful_runs = int(row.successful_runs or 0) + 1
            row.confidence = float(confidence)
            row.last_used = now
        self.db.flush()
        return row
