"""Assign each sales row its own quarter. The subject only limits the allowed range."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.utils.period_calendar import (
    fy_quarter_label,
    fy_start_for_calendar_month,
    month_label,
    parse_month_label,
    parse_quarter_label,
    quarter_of_month,
)

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_TOKEN_RE = re.compile(
    r"(\d{1,2})[-/\s]([A-Za-z]{3}|\d{1,2})[-/\s](\d{2,4})"
)


def allowed_quarter_list(parsed: Optional[Dict[str, Any]]) -> List[str]:
    raw = (parsed or {}).get("allowed_quarters")
    if isinstance(raw, (list, tuple)):
        parts = [str(item).strip().upper() for item in raw if str(item).strip()]
    else:
        parts = [part.strip().upper() for part in str(raw or "").split(",") if part.strip()]
    found = []
    for part in parts:
        token = part if part.startswith("Q") else f"Q{part}" if part in {"1", "2", "3", "4"} else part
        if token in {"Q1", "Q2", "Q3", "Q4"} and token not in found:
            found.append(token)
    if found:
        return found
    single = str((parsed or {}).get("quarter") or "").strip().upper()
    return [single] if single else []


def assign_row_periods(
    rows: Sequence[Dict[str, Any]],
    parsed: Optional[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """
    When the subject lists more than one quarter, keep or derive each row period.

    Returns (handled, warnings). A single subject quarter is left to the existing stamp.
    """
    allowed = allowed_quarter_list(parsed)
    if len(allowed) <= 1:
        return False, []
    financial_year = str((parsed or {}).get("financial_year") or "")
    warnings: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = _period_from_row(row, financial_year)
        if period:
            row["period"] = period
            row["reporting_quarter"] = period
        quarter = _quarter_token(row.get("period"))
        if quarter and quarter not in allowed:
            note = f"Row quarter {quarter} is outside the subject range {'+'.join(allowed)}"
            row["validation_warning"] = note
            row["human_review"] = True
            warnings.append(note)
            continue
        row.pop("human_review", None)
    return True, warnings


def quarter_split(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        quarter = _quarter_token((row or {}).get("period"))
        if not quarter:
            continue
        counts[quarter] = counts.get(quarter, 0) + 1
    return counts


def _period_from_row(row: Dict[str, Any], financial_year: str) -> Optional[str]:
    del financial_year
    existing = _quarter_token(row.get("period") or row.get("reporting_quarter"))
    if existing:
        spec = parse_quarter_label(str(row.get("period") or row.get("reporting_quarter") or ""))
        if spec and spec.kind == "quarter" and spec.year is not None and spec.quarter:
            return fy_quarter_label(spec.year, spec.quarter)
    parsed_date = _find_date(row)
    if parsed_date is None:
        month_hit = parse_month_label(str(row.get("source_month") or ""))
        if not month_hit:
            return None
        month, year = month_hit
    else:
        month, year = parsed_date.month, parsed_date.year
        if not str(row.get("source_month") or "").strip():
            row["source_month"] = month_label(month, year)
        row["transaction_date"] = parsed_date.isoformat()
    start = fy_start_for_calendar_month(month, year)
    return fy_quarter_label(start, quarter_of_month(month))


def _find_date(row: Dict[str, Any]) -> Optional[date]:
    for key in (
        "transaction_date",
        "date",
        "invoice_date",
        "voucher_date",
        "bill_date",
    ):
        found = _coerce_date(row.get(key))
        if found:
            return found
    return None


def _coerce_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    month_hit = parse_month_label(text)
    if month_hit:
        month, year = month_hit
        return date(year, month, 1)
    match = _TOKEN_RE.search(text)
    if not match:
        return None
    first = int(match.group(1))
    middle = match.group(2)
    year = int(match.group(3))
    if year < 100:
        year += 2000
    if middle.isdigit():
        month = int(middle)
        day = first
        if month > 12 and first <= 12:
            day, month = month, first
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            return None
    else:
        month = _MONTHS.get(middle[:3].lower())
        day = first
        if month is None:
            return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _quarter_token(value: Any) -> str:
    spec = parse_quarter_label(str(value or ""))
    if spec and spec.kind == "quarter" and spec.quarter:
        return f"Q{spec.quarter}"
    text = str(value or "").upper()
    match = re.search(r"\bQ([1-4])\b", text)
    return f"Q{match.group(1)}" if match else ""
