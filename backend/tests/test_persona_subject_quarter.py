"""Persona RBAC, email subject parsing, and quarter detection tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.dependencies.rbac import RequestUser, segment_scope_for_user
from app.enums import UserRole
from app.erp_parser.quarter_detector import detect_reporting_quarter
from app.exceptions import ForbiddenError, ValidationAppError
from app.services.segment_access_service import SegmentAccessService
from app.utils.email_subject_parser import parse_email_subject, subject_parse_error


def test_valid_subject_parsing():
    parsed = parse_email_subject("Chaudhury | South | Rubber")
    assert parsed == {
        "distributor": "Chaudhury",
        "location": "South",
        "segment": "Rubber",
        "period": None,
    }


def test_subject_with_quarter_and_full_year():
    q = parse_email_subject("Chaudhury | South | Rubber | Q2 2026")
    assert q["period"] == "Q2 2026"
    assert q["location"] == "South"
    y = parse_email_subject("Chaudhury | North | Rubber | Full Year 2026")
    assert y["period"] == "Full Year 2026"
    assert y["location"] == "North"


def test_comma_subject_rejected_with_pipe_hint():
    with pytest.raises(ValidationAppError) as exc:
        parse_email_subject("XYZ , SOUTH NBR , RUBBER")
    assert "pipes" in exc.value.message.lower() or "DISTRIBUTOR NAME | LOCATION | SEGMENT" in exc.value.message


def test_invalid_subject_raises():
    with pytest.raises(ValidationAppError):
        parse_email_subject("Bad Subject Line")
    assert subject_parse_error("Only | Two") is not None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Apr-Jun 2026", "Q1 2026"),
        ("Jul-Sep 2026", "Q2 2026"),
        ("July 2026", "Q2 2026"),
        ("Oct-Dec 2026", "Q3 2026"),
        ("Jan-Mar 2027", "Q4 2026"),
    ],
)
def test_quarter_detection_from_text_snippets(text, expected, tmp_path: Path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = f"Secondary Sales {text}"
    path = tmp_path / "sample.xlsx"
    wb.save(path)
    hit = detect_reporting_quarter(path, allow_llm_fallback=False)
    assert hit.get("reporting_quarter") == expected
    assert float(hit.get("confidence") or 0) >= 75


def test_segment_access_rubber_user():
    db = MagicMock()
    repo = MagicMock()
    repo.list_for_user.return_value = ["Rubber"]
    svc = SegmentAccessService(db)
    svc.user_segments = repo
    user = RequestUser(role=UserRole.USER, name="salesRubber", user_id=1, segments=["Rubber"])
    assert svc.can_access_segment(user, "Rubber") is True
    assert svc.can_access_segment(user, "Paper") is False
    assert svc.allowed_segments(user) == ["Rubber"]


def test_segment_access_admin_unrestricted():
    db = MagicMock()
    svc = SegmentAccessService(db)
    admin = RequestUser(role=UserRole.ADMIN, name="admin", segments=["*"])
    assert svc.is_unrestricted(admin) is True
    assert svc.allowed_segments(admin) is None
    assert svc.can_access_segment(admin, "Rubber") is True


def test_segment_access_multi_segment_user():
    db = MagicMock()
    svc = SegmentAccessService(db)
    user = RequestUser(
        role=UserRole.USER,
        name="Deb Sir",
        segments=["Paper", "Rubber", "Construction"],
    )
    assert svc.can_access_segment(user, "Paper") is True
    assert svc.can_access_segment(user, "Gloves") is False


def test_require_segment_access_forbidden():
    db = MagicMock()
    svc = SegmentAccessService(db)
    user = RequestUser(role=UserRole.USER, name="salesPaper", segments=["Paper"])
    with pytest.raises(ForbiddenError):
        svc.require_segment_access(user, "Rubber")


def test_segment_scope_for_user_none_for_admin():
    db = MagicMock()
    admin = RequestUser(role=UserRole.ADMIN, name="admin", segments=["*"])
    assert segment_scope_for_user(admin, db) is None
