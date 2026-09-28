"""Scoring jobs expose a terminal lifecycle to the email queue."""

from datetime import datetime, timezone

from app.enums import EmailProcessStatus
from app.services.outlook_sync_service import _score_view


def test_running_score_is_not_terminal():
    status, extraction, completed = _score_view(EmailProcessStatus.SCORING.value, None)
    assert status == "SCORING"
    assert extraction == "Scoring"
    assert completed is None


def test_failed_score_is_terminal():
    stamp = datetime(2026, 9, 28, tzinfo=timezone.utc)
    status, extraction, completed = _score_view(EmailProcessStatus.FAILED.value, stamp)
    assert status == "FAILED"
    assert extraction == "Failed"
    assert completed.startswith("2026-09-28")


def test_human_review_keeps_completed_extraction():
    status, extraction, completed = _score_view(
        EmailProcessStatus.HUMAN_REVIEW.value,
        datetime(2026, 9, 28, tzinfo=timezone.utc),
    )
    assert status == "HUMAN_REVIEW"
    assert extraction == "Completed"
    assert completed


def test_parsed_score_is_completed():
    status, extraction, _completed = _score_view(EmailProcessStatus.PARSED.value, None)
    assert status == "COMPLETED"
    assert extraction == "Completed"
