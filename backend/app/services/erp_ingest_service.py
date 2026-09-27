"""ERP email preview + approved import workflow."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.erp_parser import ERPParserService
from app.repositories.distributor_repository import DistributorRepository
from app.repositories.email_repository import EmailMessageRepository
from app.services.audit_service import AuditService
from app.services.erp_ingest.constants import (
    DUPLICATE_REVIEW_MESSAGE,
    MAX_EXCEL_ATTACHMENTS_PER_EMAIL,
    MIN_IMPORT_ACCURACY,
)
from app.services.erp_ingest.duplicate_service import DuplicateMixin
from app.services.erp_ingest.import_service import ImportMixin
from app.services.erp_ingest.preview_service import PreviewMixin
from app.services.erp_ingest.validation_service import ValidationMixin
from app.services.report_service import ReportService

__all__ = [
    "DUPLICATE_REVIEW_MESSAGE",
    "ERPIngestService",
    "MAX_EXCEL_ATTACHMENTS_PER_EMAIL",
    "MIN_IMPORT_ACCURACY",
]


class ERPIngestService(PreviewMixin, ImportMixin, DuplicateMixin, ValidationMixin):
    """Preview ERP attachments and import after admin approval."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.emails = EmailMessageRepository(db)
        self.distributors = DistributorRepository(db)
        self.parser = ERPParserService()
        self.reports = ReportService(db)
        self.audit = AuditService(db)

    def resolve_distributor_from_subject(self, email: Any) -> Optional[Dict[str, Any]]:
        """Resolve distributor from parsed email subject (business identity)."""
        if not getattr(email, "subject_valid", False) or not email.parsed_distributor:
            return None
        dist = self.distributors.get_or_create_by_company(
            email.parsed_distributor,
            representative_name=email.parsed_distributor,
        )
        if not dist.is_active or dist.is_deleted:
            return None
        return {
            "id": dist.id,
            "company": dist.company or dist.name,
            "name": dist.name,
            "email": dist.email,
            "match": "subject",
        }

    def _preferred_parser_pair(self, email: Any) -> Tuple[Optional[str], Optional[str]]:
        """Saved parser plus fingerprint. A weak profile is not reused."""
        match = self.resolve_distributor_from_subject(email)
        if not match:
            return None, None
        from app.repositories.parser_profile_repository import ParserProfileRepository

        profile = ParserProfileRepository(self.db).get_by_distributor(int(match["id"]))
        if profile is None:
            return None, None
        fingerprint = (profile.fingerprint_hash or "").strip() or None
        if float(profile.confidence or 0) < 90:
            return None, fingerprint
        return profile.parser_strategy, fingerprint

    def _known_profiles(self, email: Any) -> List[Dict[str, Any]]:
        """High-confidence layouts saved for this distributor. None are overwritten."""
        match = self.resolve_distributor_from_subject(email)
        if not match:
            return []
        from app.repositories.parser_profile_repository import ParserProfileRepository

        profiles: List[Dict[str, Any]] = []
        for profile in ParserProfileRepository(self.db).list_for_distributor(int(match["id"])):
            fingerprint = (profile.fingerprint_hash or "").strip() or None
            if float(profile.confidence or 0) < 90 or not fingerprint:
                continue
            profiles.append(
                {
                    "parser": profile.parser_strategy,
                    "fingerprint": fingerprint,
                    "confidence": float(profile.confidence or 0),
                }
            )
        return profiles

    def _preferred_parser_name(self, email: Any) -> Optional[str]:
        """Reuse the last high-confidence parser for this distributor."""
        name, _fingerprint = self._preferred_parser_pair(email)
        return name

    def _remember_parser(self, email: Any, preview: Dict[str, Any]) -> None:
        match = self.resolve_distributor_from_subject(email)
        if not match:
            return
        confidence = float(preview.get("orchestrator_confidence") or 0)
        breakdown = (preview.get("confidence") or {}).get("breakdown") or {}
        strategy = str(breakdown.get("parser_name") or "")
        if confidence < 90 or not strategy:
            return
        from app.repositories.parser_profile_repository import ParserProfileRepository

        ParserProfileRepository(self.db).upsert(
            int(match["id"]),
            strategy,
            confidence,
            parser_name=strategy,
            parser_version=str(breakdown.get("parser_version") or "") or None,
            layout_type=str(breakdown.get("layout_name") or breakdown.get("layout") or "") or None,
            fingerprint_hash=str(breakdown.get("fingerprint") or "") or None,
        )

    def resolve_distributors_for_sender(self, sender_email: str) -> List[Dict[str, Any]]:
        """Match distributor(s) by sender email (legacy fallback)."""
        email = (sender_email or "").strip().lower()
        if not email:
            return []
        dist = self.distributors.get_by_email(sender_email)
        if dist is not None and dist.is_active and not dist.is_deleted:
            return [
                {
                    "id": dist.id,
                    "company": dist.company,
                    "name": dist.name,
                    "email": dist.email,
                    "match": "exact",
                }
            ]
        matches: List[Dict[str, Any]] = []
        for d in self.distributors.list(skip=0, limit=500):
            if not d.is_active or d.is_deleted:
                continue
            demail = (d.email or "").strip().lower()
            if demail and demail == email:
                matches.append(
                    {
                        "id": d.id,
                        "company": d.company,
                        "name": d.name,
                        "email": d.email,
                        "match": "exact",
                    }
                )
        return matches

    def list_active_distributors(self) -> List[Dict[str, Any]]:
        """Dropdown options when sender does not match."""
        out: List[Dict[str, Any]] = []
        for d in self.distributors.list(skip=0, limit=500):
            if not d.is_active or d.is_deleted:
                continue
            out.append(
                {
                    "id": d.id,
                    "company": d.company,
                    "name": d.name,
                    "email": d.email,
                }
            )
        return out

