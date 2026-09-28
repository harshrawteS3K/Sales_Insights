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
from typing import Any, Dict, Optional

from app.constants.business_segments import (
    BUSINESS_SEGMENTS,
    SEGMENT_ALIASES,
    normalize_business_segment,
)
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

# Q1+Q2 FY 2026-27 | Q1+Q2 2026-27 | Q2+Q3+Q4 2026-27
_QUARTER_LIST_RE = re.compile(
    r"^\s*((?:Q\s*[1-4]\s*\+\s*)*Q\s*[1-4])\s+(?:FY\s*)?(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*$",
    re.IGNORECASE,
)
_MONTH_TOKEN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
# APRIL+MAY 2026-27 | APR+JUN FY 2026-27 | APRIL+MAY 2026
_MONTH_LIST_RE = re.compile(
    rf"^\s*((?:{_MONTH_TOKEN}\s*\+\s*)+{_MONTH_TOKEN})\s+"
    rf"(?:FY\s*)?(\d{{4}})(?:\s*[-–—/]\s*(\d{{2}}|\d{{4}}))?\s*$",
    re.IGNORECASE,
)
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


def multi_quarter_scope(raw: Optional[str]) -> Optional[Dict[str, str]]:
    """Quarter or month list plus a year span. ``FY`` is optional. One quarter returns None."""
    parsed = _period_span(raw)
    if not parsed or len(parsed["quarters"]) < 2:
        return None
    fy_start = parsed["fy_start"]
    return {
        "allowed_quarters": ",".join(parsed["quarters"]),
        "financial_year": f"{fy_start}-{(fy_start + 1) % 100:02d}",
        "period": fy_annual_label(fy_start),
    }


def _period_span(raw: Optional[str]) -> Optional[Dict[str, object]]:
    """Parse ``Q1+Q2 2026-27`` or ``APRIL+JULY 2026-27``. Malformed tokens return None."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return None
    quarter_match = _QUARTER_LIST_RE.match(text)
    if quarter_match:
        fy_start = int(quarter_match.group(2))
        if not _fy_end_ok(fy_start, quarter_match.group(3)):
            return None
        quarters = []
        for number in re.findall(r"Q\s*([1-4])", quarter_match.group(1), flags=re.IGNORECASE):
            label = f"Q{number}"
            if label not in quarters:
                quarters.append(label)
        if not quarters:
            return None
        return {"quarters": quarters, "fy_start": fy_start}

    month_match = _MONTH_LIST_RE.match(text)
    if not month_match:
        return None
    fy_start = int(month_match.group(2))
    end_raw = month_match.group(3)
    if end_raw and not _fy_end_ok(fy_start, end_raw):
        return None
    from app.utils.period_calendar import quarter_of_month

    quarters = []
    for token in re.split(r"\s*\+\s*", month_match.group(1)):
        hit = parse_month_label(f"{token} {fy_start}")
        if not hit:
            return None
        month, _year = hit
        label = f"Q{quarter_of_month(month)}"
        if label not in quarters:
            quarters.append(label)
    if not quarters:
        return None
    return {"quarters": quarters, "fy_start": fy_start}


def normalize_subject_period(raw: Optional[str]) -> Optional[str]:
    """
    Normalize optional 4th subject part into a canonical FY period label.

    Returns e.g. ``FY 2025-26 • Q2`` or ``FY 2025-26``, or None if empty.
    """
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return None

    multi = multi_quarter_scope(text)
    if multi:
        return multi["period"]

    span = _period_span(text)
    if span and len(span["quarters"]) == 1:
        quarter_number = int(str(span["quarters"][0])[1])
        return fy_quarter_label(int(span["fy_start"]), quarter_number)

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


def _period_token_ok(token: str) -> bool:
    try:
        return normalize_subject_period(token) is not None
    except ValidationAppError:
        return False


def _unit_token_ok(token: str) -> bool:
    text = re.sub(r"\s+", " ", (token or "").strip()).upper()
    if not text:
        return False
    try:
        normalize_subject_unit(text)
        return True
    except ValidationAppError:
        return False


def _known_segment(token: str) -> Optional[str]:
    key = " ".join((token or "").strip().split()).casefold()
    if not key:
        return None
    if key in SEGMENT_ALIASES:
        return SEGMENT_ALIASES[key]
    for name in BUSINESS_SEGMENTS:
        if name.casefold() == key:
            return name
    return None


def _region_and_segment(token: str) -> Optional[tuple]:
    """``WEST RUBBER`` → (``WEST``, ``Rubber``). Unknown suffixes stay unsplit."""
    words = " ".join((token or "").strip().split()).split(" ")
    if len(words) < 2:
        return None
    for size in range(len(words) - 1, 0, -1):
        segment = _known_segment(" ".join(words[-size:]))
        region = " ".join(words[:-size]).strip()
        if segment and region:
            return region, segment
    return None


def parse_email_subject(subject: Optional[str]) -> Dict[str, Any]:
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

    raw_parts = [p.strip() for p in _SUBJECT_SPLIT_RE.split(raw) if p.strip()]
    parts = [_title_value(p) for p in raw_parts]
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

    # ``Distributor|WEST RUBBER|Q1 FY 2026-27|KG`` keeps region and segment in one token.
    compact = None
    if len(raw_parts) == 4 and _period_token_ok(raw_parts[2]) and _unit_token_ok(raw_parts[3]):
        compact = _region_and_segment(raw_parts[1])

    if compact:
        distributor = _title_value(raw_parts[0])
        location = _title_value(compact[0])
        segment = compact[1]
        period_token = raw_parts[2]
        unit = normalize_subject_unit(raw_parts[3])
    else:
        distributor, location, segment_raw = parts[0], parts[1], parts[2]
        segment = normalize_business_segment(segment_raw)
        period_token = raw_parts[3] if len(raw_parts) >= 4 else ""
        unit = normalize_subject_unit(raw_parts[4] if len(raw_parts) == 5 else None)
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

    # Period token stays in its original spelling so FY parsing is unchanged.
    period = None
    source_month = None
    if period_token:
        source_month = source_month_from_period_token(period_token)
        period = normalize_subject_period(period_token)

    financial_year: Optional[str] = None
    quarter: Optional[str] = None
    allowed_quarters = ""
    multi = multi_quarter_scope(period_token) if period_token else None
    if multi:
        financial_year = multi["financial_year"]
        allowed_quarters = multi["allowed_quarters"]
        period = multi["period"]
    elif period:
        spec = parse_quarter_label(period)
        if spec and spec.year is not None:
            financial_year = fy_short(spec.year)
            if spec.kind == "quarter" and spec.quarter:
                quarter = f"Q{spec.quarter}"
                allowed_quarters = quarter

    quarter_values = [part for part in str(allowed_quarters or "").split(",") if part]

    return {
        "distributor": distributor,
        "location": location,
        "region": location,
        "segment": segment,
        "period": period,
        "financial_year": financial_year,
        "quarter": quarter,
        "allowed_quarters": quarter_values,
        "source_month": source_month,
        "unit": unit,
    }


def try_parse_email_subject(subject: Optional[str]) -> Optional[Dict[str, Any]]:
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
