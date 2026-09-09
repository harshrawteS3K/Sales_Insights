"""Fiscal-year quarter helpers for monthly-pivot ERP workbooks.

APCOTEX quarters (same as frontend):
  Q1 = Apr–Jun
  Q2 = Jul–Sep
  Q3 = Oct–Dec
  Q4 = Jan–Mar (calendar year = FY start + 1)
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

# Month key (normalized) → fiscal quarter number
MONTH_TO_FY_QUARTER: Dict[str, int] = {
    "april": 1,
    "apr": 1,
    "may": 1,
    "june": 1,
    "jun": 1,
    "july": 2,
    "jul": 2,
    "august": 2,
    "aug": 2,
    "september": 2,
    "sep": 2,
    "sept": 2,
    "october": 3,
    "oct": 3,
    "november": 3,
    "nov": 3,
    "december": 3,
    "dec": 3,
    "january": 4,
    "jan": 4,
    "february": 4,
    "feb": 4,
    "march": 4,
    "mar": 4,
}


def current_fy_start_year(today: Optional[date] = None) -> int:
    """FY starts in April: Apr 2026 → 2026; Jan 2026 → 2025."""
    d = today or date.today()
    return d.year if d.month >= 4 else d.year - 1


def month_key_to_quarter(month_key: str) -> Optional[int]:
    return MONTH_TO_FY_QUARTER.get((month_key or "").strip().lower())


def quarter_label(fy_start_year: int, quarter: int) -> str:
    """Label stored on reports / sales.period, e.g. ``Q1 2025``."""
    return f"Q{quarter} {fy_start_year}"


def resolve_fy_start_year(
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
) -> int:
    """
    Prefer explicit FY start; else year from ``Q3 2026``-style label; else current FY.
    """
    if fiscal_year_start and 1990 <= int(fiscal_year_start) <= 2100:
        return int(fiscal_year_start)
    raw = (reporting_quarter or "").strip()
    if raw.upper().startswith("Q") and len(raw) >= 3:
        parts = raw.replace("  ", " ").split()
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
    return current_fy_start_year()


def group_month_indexes_by_quarter(
    month_columns: List[Tuple[int, str, str]],
) -> Dict[int, List[int]]:
    """
    ``month_columns`` items are ``(col_index, original_header, month_key)``.
    Returns ``{1: [idxs], 2: [...], ...}`` for quarters that have at least one column.
    """
    grouped: Dict[int, List[int]] = {1: [], 2: [], 3: [], 4: []}
    for idx, _header, key in month_columns:
        q = month_key_to_quarter(key)
        if q:
            grouped[q].append(idx)
    return {q: cols for q, cols in grouped.items() if cols}
