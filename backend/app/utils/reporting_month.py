"""Reporting month normalization helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional


_ISO_DT = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?"
)


def normalize_reporting_month(value: object) -> str:
    """
    Normalize Reporting Month to a stable business key string.

    Excel often stores months as date cells (``2026-07-01``). Those must become
    ``July 2026`` so Distributor + Reporting Month identity matches across uploads.

    Already-human values (``July 2026``, ``Q2 FY26``) are returned trimmed as-is.
    """
    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.strftime("%B %Y")
    if isinstance(value, date):
        return value.strftime("%B %Y")

    # Excel serial numbers occasionally appear as int/float
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            # Excel epoch 1899-12-30
            from datetime import timedelta

            serial = float(value)
            if 20000 < serial < 80000:  # rough sane range for 1950–2100
                dt = datetime(1899, 12, 30) + timedelta(days=serial)
                return dt.strftime("%B %Y")
        except (OverflowError, ValueError):
            pass

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "nat"}:
        return ""

    # Datetime/date string from openpyxl str() or DB backfill
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


def months_equivalent(a: Optional[str], b: Optional[str]) -> bool:
    """True when two reporting-month strings resolve to the same business key."""
    na = normalize_reporting_month(a)
    nb = normalize_reporting_month(b)
    if not na or not nb:
        return False
    return na.casefold() == nb.casefold()
