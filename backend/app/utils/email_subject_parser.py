"""Parse distributor email subjects: ``DISTRIBUTOR | LOCATION | SEGMENT [| PERIOD]``.

Period forms (Indian FY Apr–Mar):
  Monthly   — ``APRIL 2026`` (stored as FY quarter; month is never kept)
  Quarterly — ``Q2 FY 2025-26``
  Annual    — ``FY 2025-26``

Also accepts ``FY 2025-26 • Q2``, legacy ``Q2 2025``, and ``Full Year 2025``.
Canonical stored period: ``FY 2025-26 • Q2`` or ``FY 2025-26``.

Resolved fields also include ``financial_year`` (e.g. ``FY 2025-26``) and
``quarter`` (e.g. ``Q2``) when the period is present.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from app.constants.business_segments import normalize_business_segment
from app.exceptions import ValidationAppError
from app.utils.period_calendar import (
    fy_annual_label,
    fy_quarter_label,
    fy_short,
    month_label,
    parse_month_label,
    parse_quarter_label,
)

EXPECTED_SUBJECT_FORMAT = "DISTRIBUTOR NAME | LOCATION | SEGMENT | PERIOD | UNIT"
EXPECTED_SUBJECT_EXAMPLE = "Chaudhury | South | Rubber | Q2 FY 2025-26 | MT"
EXPECTED_SUBJECT_EXAMPLE_YEAR = "Chaudhury | South | Rubber | FY 2025-26 | KG"
EXPECTED_SUBJECT_EXAMPLE_MONTH = "Reda | South | Construction | APRIL 2026 | KG"

_UNIT_CANONICAL = {
    "KG": "KG",
    "KGS": "KG",
    "MT": "MT",
    "TON": "TON",
    "TONS": "TON",
    "TONNE": "TON",
    "TONNES": "TON",
}

# Pipe (or spaced hyphen / em/en-dash) only — commas are NOT valid separators.
# Repeated pipes and surrounding spaces are one separator.
_SUBJECT_SPLIT_RE = re.compile(r"\s*(?:\|+|\s-\s|–|—)\s*")

# Q2 FY 2025-26  |  Q2 FY2025-26
_Q_FY_RE = re.compile(
    r"^\s*Q\s*([1-4])\s+FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*$",
    re.IGNORECASE,
)
# FY 2025-26 • Q2  |  FY 2025–26 Q2
_FY_Q_RE = re.compile(
    r"^\s*FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*[•·.\-]?\s*Q\s*([1-4])\s*$",
    re.IGNORECASE,
)
# FY 2025-26 (annual)
_FY_ANNUAL_RE = re.compile(
    r"^\s*FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*$",
    re.IGNORECASE,
)
# Full Year 2025 / Complete Year / Annual / FY 2025 (single year = FY start)
_FULL_YEAR_RE = re.compile(
    r"^(?:full\s*year|complete\s*year|whole\s*year|annual|fy|year)"
    r"[\s\-–—/]*(\d{4})(?:\s*[-–—/]\s*\d{2,4})?$",
    re.IGNORECASE,
)
# Legacy: Q2 2025 (year = FY start)
_LEGACY_Q_RE = re.compile(r"^\s*Q\s*([1-4])\s+(\d{4})\s*$", re.IGNORECASE)


def _title_value(raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return ""
    if text.isupper() and len(text) <= 6:
        return text.title()
    return text.title()


def _fy_end_ok(start: int, end_raw: str) -> bool:
    end_raw = (end_raw or "").strip()
    expected_yy = f"{(start + 1) % 100:02d}"
    if len(end_raw) == 2:
        return end_raw == expected_yy
    if len(end_raw) == 4 and end_raw.isdigit():
        return int(end_raw) == start + 1
    return False


def normalize_subject_unit(raw: Optional[str]) -> str:
    """Canonical subject unit: KG, MT, or TON. Blank defaults to MT."""
    text = re.sub(r"\s+", " ", (raw or "").strip()).upper()
    if not text:
        return "MT"
    if text not in _UNIT_CANONICAL:
        raise ValidationAppError(
            "Invalid unit in subject. Use KG, MT, TON, or TONS. "
            f"Example: {EXPECTED_SUBJECT_EXAMPLE_MONTH}",
            details={"unit": raw, "expected": "KG | MT | TON | TONS"},
        )
    return _UNIT_CANONICAL[text]


def source_month_from_period_token(raw: Optional[str]) -> Optional[str]:
    """``APRIL 2026`` → ``April 2026``. Quarter and annual tokens return None."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return None
    hit = parse_month_label(text)
    if not hit:
        return None
    month, year = hit
    return month_label(month, year)


def normalize_subject_period(raw: Optional[str]) -> Optional[str]:
    """
    Normalize optional 4th subject part into a canonical FY period label.

    Returns e.g. ``FY 2025-26 • Q2`` or ``FY 2025-26``, or None if empty.
    """
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return None

    # Monthly subject (APRIL 2026) → Indian FY quarter. Month is kept separately.
    from app.utils.period_calendar import quarter_of_month, fy_start_for_calendar_month

    month_hit = parse_month_label(text)
    if month_hit:
        month, year = month_hit
        return fy_quarter_label(fy_start_for_calendar_month(month, year), quarter_of_month(month))

    # Prefer shared calendar parser (handles display forms, months, legacy)
    spec = parse_quarter_label(text)
    if spec and spec.year is not None:
        if spec.kind == "year":
            return fy_annual_label(spec.year)
        if spec.kind == "quarter" and spec.quarter:
            return fy_quarter_label(spec.year, spec.quarter)

    m = _Q_FY_RE.match(text)
    if m:
        fy_start = int(m.group(2))
        if _fy_end_ok(fy_start, m.group(3)):
            return fy_quarter_label(fy_start, int(m.group(1)))

    m = _FY_Q_RE.match(text)
    if m:
        fy_start = int(m.group(1))
        if _fy_end_ok(fy_start, m.group(2)):
            return fy_quarter_label(fy_start, int(m.group(3)))

    m = _FY_ANNUAL_RE.match(text)
    if m:
        fy_start = int(m.group(1))
        if _fy_end_ok(fy_start, m.group(2)):
            return fy_annual_label(fy_start)

    m = _FULL_YEAR_RE.match(text)
    if m:
        return fy_annual_label(int(m.group(1)))

    m = _LEGACY_Q_RE.match(text)
    if m:
        return fy_quarter_label(int(m.group(2)), int(m.group(1)))

    raise ValidationAppError(
        f"Invalid period in subject. Use a month (APRIL 2026), a quarter "
        f"(Q2 FY 2025-26), or an annual year (FY 2025-26). "
        f"Example: {EXPECTED_SUBJECT_EXAMPLE_MONTH}",
        details={"period": raw, "expected": "APRIL 2026 | Q2 FY 2025-26 | FY 2025-26"},
    )


def parse_email_subject(subject: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Parse ``DISTRIBUTOR | LOCATION | SEGMENT | PERIOD | UNIT``.

    PERIOD examples: ``APRIL 2026``, ``Q2 FY 2026-27``, ``FY 2026-27``.
    UNIT examples: ``KG``, ``MT``, ``TON``, ``TONS``. Unit is optional for older subjects.
    Returns distributor, location, segment, period, financial_year, quarter,
    source_month, and unit.
    """
    raw = (subject or "").strip()
    if not raw:
        raise ValidationAppError(
            f"Invalid email subject. Expected format: {EXPECTED_SUBJECT_FORMAT}",
            details={
                "subject": subject,
                "expected": EXPECTED_SUBJECT_FORMAT,
                "example": EXPECTED_SUBJECT_EXAMPLE,
            },
        )

    if "," in raw and "|" not in raw and " - " not in raw:
        raise ValidationAppError(
            f"Invalid email subject. Use pipes, not commas. Expected: {EXPECTED_SUBJECT_FORMAT} "
            f"(example: {EXPECTED_SUBJECT_EXAMPLE})",
            details={
                "subject": subject,
                "expected": EXPECTED_SUBJECT_FORMAT,
                "example": EXPECTED_SUBJECT_EXAMPLE,
            },
        )

    parts = [_title_value(p) for p in _SUBJECT_SPLIT_RE.split(raw) if p.strip()]
    if len(parts) not in (3, 4, 5):
        raise ValidationAppError(
            f"Invalid email subject. Expected 3 to 5 parts: {EXPECTED_SUBJECT_FORMAT} "
            f"(examples: {EXPECTED_SUBJECT_EXAMPLE_MONTH} · {EXPECTED_SUBJECT_EXAMPLE})",
            details={
                "subject": subject,
                "parts_found": len(parts),
                "expected": EXPECTED_SUBJECT_FORMAT,
                "example": EXPECTED_SUBJECT_EXAMPLE,
            },
        )

    distributor, location, segment_raw = parts[0], parts[1], parts[2]
    period_raw = parts[3] if len(parts) >= 4 else None
    unit_raw = parts[4] if len(parts) == 5 else None
    segment = normalize_business_segment(segment_raw)
    if not distributor or not location or not segment:
        raise ValidationAppError(
            f"Invalid email subject. Distributor, Location, and Segment must all be non-empty. "
            f"Expected: {EXPECTED_SUBJECT_FORMAT}",
            details={
                "subject": subject,
                "expected": EXPECTED_SUBJECT_FORMAT,
                "example": EXPECTED_SUBJECT_EXAMPLE,
            },
        )

    # Period token should not be title-cased (breaks FY parsing) — re-read raw part
    raw_parts = [p.strip() for p in _SUBJECT_SPLIT_RE.split(raw) if p.strip()]
    period = None
    source_month = None
    if period_raw:
        period_token = raw_parts[3] if len(raw_parts) >= 4 else period_raw
        source_month = source_month_from_period_token(period_token)
        period = normalize_subject_period(period_token)
    unit = normalize_subject_unit(raw_parts[4] if len(raw_parts) == 5 else unit_raw)

    financial_year: Optional[str] = None
    quarter: Optional[str] = None
    if period:
        spec = parse_quarter_label(period)
        if spec and spec.year is not None:
            financial_year = fy_short(spec.year)
            if spec.kind == "quarter" and spec.quarter:
                quarter = f"Q{spec.quarter}"

    return {
        "distributor": distributor,
        "location": location,
        "segment": segment,
        "period": period,
        "financial_year": financial_year,
        "quarter": quarter,
        "source_month": source_month,
        "unit": unit,
    }


def try_parse_email_subject(subject: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """Return parsed subject dict or None when invalid (no exception)."""
    try:
        return parse_email_subject(subject)
    except ValidationAppError:
        return None


def subject_parse_error(subject: Optional[str]) -> Optional[str]:
    """Human-readable validation message for UI, or None if valid."""
    try:
        parse_email_subject(subject)
        return None
    except ValidationAppError as exc:
        return exc.message


def build_email_subject(
    distributor_name: str,
    location: Optional[str] = None,
    segment: Optional[str] = None,
    *,
    period_label: Optional[str] = None,
    quarter: Optional[int] = None,
    year: Optional[int] = None,
    annual: bool = False,
) -> str:
    """Build canonical subject with optional FY period."""
    parts = [
        (distributor_name or "").strip(),
        (location or "").strip(),
        normalize_business_segment(segment) or (segment or "").strip() or "General",
    ]
    period = None
    if period_label:
        period = normalize_subject_period(period_label)
    elif annual and year is not None:
        period = fy_annual_label(int(year))
    elif quarter is not None and year is not None:
        period = f"Q{int(quarter)} {fy_short(int(year))}"
    elif year is not None:
        period = fy_annual_label(int(year))

    if period:
        # Prefer subject-friendly quarterly form
        spec = parse_quarter_label(period)
        if spec and spec.kind == "quarter" and spec.year and spec.quarter:
            parts.append(f"Q{spec.quarter} {fy_short(spec.year)}")
        else:
            parts.append(period)

    return " | ".join(parts)
