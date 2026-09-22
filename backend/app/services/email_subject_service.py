"""Parse and persist distributor email subject metadata."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction, EmailProcessStatus
from app.exceptions import ValidationAppError
from app.models.email_message import EmailMessage
from app.schemas.audit import AuditTrailCreate
from app.services.audit_service import AuditService
from app.utils.email_subject_parser import parse_email_subject, subject_parse_error

logger = get_logger(__name__)


class EmailSubjectService:
    """Apply ``Distributor | Location | Segment`` parsing to email records."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def apply_to_email(
        self,
        email: EmailMessage,
        *,
        actor: str = "system",
        skip_if_valid: bool = False,
    ) -> bool:
        """
        Parse subject and update email fields.

        Returns ``True`` when subject is valid; sets ``INVALID_SUBJECT`` status otherwise.
        """
        if skip_if_valid and email.subject_valid and email.parsed_distributor:
            return True

        try:
            parsed = parse_email_subject(email.subject)
        except ValidationAppError:
            err = subject_parse_error(email.subject) or "Invalid email subject"
            email.parsed_distributor = None
            email.parsed_location = None
            email.parsed_segment = None
            email.subject_valid = False
            if email.process_status not in {
                EmailProcessStatus.INSERTED.value,
                EmailProcessStatus.MARKED_READ.value,
            }:
                email.process_status = EmailProcessStatus.INVALID_SUBJECT.value
            email.error_message = err
            self.db.flush()
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action="Email Subject Parsed",
                    details=f"Invalid subject for email_id={email.id}: {err}",
                    module="Email Extraction",
                    status="Failed",
                    entity_type="email",
                    entity_id=str(email.id),
                    extra_metadata={"subject": email.subject, "valid": False},
                )
            )
            logger.warning(
                "Invalid email subject | email_id={} | subject={!r}",
                email.id,
                email.subject,
            )
            return False

        email.parsed_distributor = parsed["distributor"]
        email.parsed_location = parsed["location"]
        email.parsed_segment = parsed["segment"]
        # Optional 4th part: Q2 FY 2025-26 / FY 2025-26 — prefer over workbook detection later
        if parsed.get("period"):
            email.detected_quarter = parsed["period"]
        email.subject_valid = True
        if email.process_status == EmailProcessStatus.INVALID_SUBJECT.value:
            email.process_status = EmailProcessStatus.UNREAD.value
        if email.error_message and "Invalid email subject" in (email.error_message or ""):
            email.error_message = None
        self.db.flush()
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action="Email Subject Parsed",
                details=(
                    f"Parsed subject for email_id={email.id} | "
                    f"distributor={parsed['distributor']} | location={parsed['location']} | "
                    f"segment={parsed['segment']}"
                    + (f" | period={parsed['period']}" if parsed.get("period") else "")
                ),
                module="Email Extraction",
                status="Success",
                entity_type="email",
                entity_id=str(email.id),
                extra_metadata={
                    "subject": email.subject,
                    "valid": True,
                    "segment": parsed["segment"],
                    "distributor": parsed["distributor"],
                    "location": parsed["location"],
                    "period": parsed.get("period"),
                },
            )
        )
        return True

    @staticmethod
    def require_valid_subject(email: EmailMessage) -> None:
        """Raise when email subject is not in the expected pipe format."""
        if not email.subject_valid or not email.parsed_distributor:
            raise ValidationAppError(
                subject_parse_error(email.subject)
                or "Invalid email subject. Expected: DISTRIBUTOR NAME | LOCATION | SEGMENT | PERIOD",
                details={"email_id": email.id, "subject": email.subject},
            )
