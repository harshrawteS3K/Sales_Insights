"""Reporting month / quarter normalization helpers (Indian FY)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from app.utils.period_calendar import format_period_display, parse_quarter_label

_ISO_DT = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?"
)

# Rejected invalid shapes
_BAD_Q_DASH = re.compile(r"^Q[1-4]\s*[-/]\s*\d{4}$", flags=re.IGNORECASE)
_BAD_Q5 = re.compile(r"^Q[5-9]", flags=re.IGNORECASE)
_BAD_YEAR_Q = re.compile(r"^\d{4}\s*Q[1-4]\b", flags=re.IGNORECASE)
_BAD_QUARTER_WORD = re.compile(r"^quarter\s*\d", flags=re.IGNORECASE)


def normalize_reporting_month(value: object) -> str:
    """
    Normalize Reporting Quarter / Month to a stable business key string.

    Quarters → canonical Indian FY label:
      - ``Q1 2025``, ``FY 2025-26 • Q1`` → ``FY 2025-26 • Q1``
      - ``FY 2025-26`` (annual) → ``FY 2025-26``

    Months (legacy):
      - ``July 2026``, Excel date cells → ``July 2026``
    """
    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.strftime("%B %Y")
    if isinstance(value, date):
        return value.strftime("%B %Y")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            from datetime import timedelta

            serial = float(value)
            if 20000 < serial < 80000:
                dt = datetime(1899, 12, 30) + timedelta(days=serial)
                return dt.strftime("%B %Y")
        except (OverflowError, ValueError):
            pass

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "nat"}:
        return ""

    collapsed = re.sub(r"\s+", " ", text).strip()

    if _BAD_Q_DASH.match(collapsed):
        return ""
    if _BAD_Q5.match(collapsed):
        return ""
    if _BAD_YEAR_Q.match(collapsed):
        return ""
    if _BAD_QUARTER_WORD.match(collapsed):
        return ""

    # Strip display range paren before parsing
    for_parse = re.sub(
        r"\s*\((?:Apr|Jul|Oct|Jan)[^)]*\)\s*$",
        "",
        collapsed,
        flags=re.IGNORECASE,
    ).strip()

    spec = parse_quarter_label(for_parse)
    if spec and spec.year is not None and spec.kind in {"quarter", "year"}:
        return spec.label

    match = _ISO_DT.match(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        try:
            return date(year, month, 1).strftime("%B %Y")
        except ValueError:
            return text

    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%B %Y")
        except ValueError:
            continue

    return text


def display_reporting_period(value: object) -> str:
    """UI display for a reporting period key."""
    key = normalize_reporting_month(value)
    if not key:
        return ""
    return format_period_display(key)


def months_equivalent(a: Optional[str], b: Optional[str]) -> bool:
    """True when two reporting-month strings resolve to the same business key."""
    na = normalize_reporting_month(a)
    nb = normalize_reporting_month(b)
    if not na or not nb:
        return False
    if na.casefold() == nb.casefold():
        return True
    # Compare via period specs (legacy vs FY label)
    sa = parse_quarter_label(na)
    sb = parse_quarter_label(nb)
    if sa and sb and sa.label and sb.label:
        return sa.label.casefold() == sb.label.casefold()
    return False
