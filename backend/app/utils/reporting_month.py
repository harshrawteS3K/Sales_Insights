"""Reporting month / quarter normalization helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional


_ISO_DT = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?"
)

# Strict: "Q1 2026" / "q1  2026" — space(s) between quarter and year only
_QUARTER_STRICT = re.compile(r"^Q([1-4])\s+(\d{4})$", flags=re.IGNORECASE)


def normalize_reporting_month(value: object) -> str:
    """
    Normalize Reporting Quarter / Month to a stable business key string.

    Quarters (strict):
      - ``Q1 2026``, ``q3 2026`` → ``Q3 2026``
      - Rejects: ``Q1-2026``, ``2026 Q1``, ``Quarter1``, ``Q5 2026``

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

    # Collapse internal whitespace for quarter matching
    collapsed = re.sub(r"\s+", " ", text).strip()
    quarter = _QUARTER_STRICT.match(collapsed)
    if quarter:
        return f"Q{quarter.group(1)} {quarter.group(2)}"

    # Reject explicit invalid quarter shapes (Prompt 1A)
    if re.match(r"^Q[1-4]\s*[-/]\s*\d{4}$", collapsed, flags=re.IGNORECASE):
        return ""  # Q1-2026 / Q1/2026
    if re.match(r"^Q[5-9]", collapsed, flags=re.IGNORECASE):
        return ""  # Q5 …
    if re.match(r"^\d{4}\s*Q[1-4]\b", collapsed, flags=re.IGNORECASE):
        return ""  # 2026 Q1
    if re.match(r"^quarter\s*\d", collapsed, flags=re.IGNORECASE):
        return ""  # Quarter1

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
