"""Shared calendar helpers for Monthly → Quarterly → Yearly rollups.

Calendar year quarters (Q1=Jan–Mar). Designed so FY / half-year / custom
ranges can be added without changing callers — only expand PeriodSpec builders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_MONTH_INDEX = {name.lower(): i + 1 for i, name in enumerate(_MONTH_NAMES)}

# Calendar quarters (not Indian FY)
_QUARTER_MONTHS = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}

_QUARTER_LABEL_RE = re.compile(r"^\s*Q([1-4])\s+(\d{4})\s*$", re.IGNORECASE)
_MONTH_LABEL_RE = re.compile(
    r"^\s*(" + "|".join(_MONTH_NAMES) + r")\s+(\d{4})\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PeriodSpec:
    """Resolved set of reporting-month labels for a business period."""

    label: str
    kind: str  # "quarter" | "year" | "half" | "custom" | "month"
    year: Optional[int]
    months: Tuple[str, ...]

    @property
    def month_list(self) -> List[str]:
        return list(self.months)


def month_label(month: int, year: int) -> str:
    """Return canonical ``January 2026`` label."""
    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}")
    return f"{_MONTH_NAMES[month - 1]} {int(year)}"


def parse_month_label(label: str) -> Optional[Tuple[int, int]]:
    """Parse ``January 2026`` → (month, year)."""
    if not label:
        return None
    match = _MONTH_LABEL_RE.match(label.strip())
    if not match:
        return None
    month = _MONTH_INDEX[match.group(1).lower()]
    year = int(match.group(2))
    return month, year


def quarter_of_month(month: int) -> int:
    """Calendar quarter 1–4 for a month number."""
    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}")
    return (month - 1) // 3 + 1


def months_for_quarter(quarter: int, year: int) -> Tuple[str, ...]:
    """Q1 2026 → (January 2026, February 2026, March 2026)."""
    q = int(quarter)
    if q not in _QUARTER_MONTHS:
        raise ValueError(f"Invalid quarter: {quarter}")
    return tuple(month_label(m, year) for m in _QUARTER_MONTHS[q])


def period_spec_for_quarter(quarter: int, year: int) -> PeriodSpec:
    """Build a PeriodSpec for a calendar quarter."""
    months = months_for_quarter(quarter, year)
    return PeriodSpec(
        label=f"Q{int(quarter)} {int(year)}",
        kind="quarter",
        year=int(year),
        months=months,
    )


def parse_quarter_label(label: str) -> Optional[PeriodSpec]:
    """Parse ``Q1 2026`` into a PeriodSpec."""
    if not label:
        return None
    match = _QUARTER_LABEL_RE.match(label.strip())
    if not match:
        return None
    return period_spec_for_quarter(int(match.group(1)), int(match.group(2)))


def resolve_period(
    *,
    quarter: Optional[int] = None,
    year: Optional[int] = None,
    quarter_label: Optional[str] = None,
    months: Optional[Sequence[str]] = None,
) -> PeriodSpec:
    """
    Resolve a business period from any supported input shape.

    Prefer ``quarter_label`` (``Q1 2026``) or ``quarter``+``year``.
    ``months`` enables custom / half-year / FY ranges later.
    """
    if quarter_label:
        spec = parse_quarter_label(quarter_label)
        if spec:
            return spec
        raise ValueError(f"Invalid quarter label: {quarter_label!r}")
    if quarter is not None and year is not None:
        return period_spec_for_quarter(int(quarter), int(year))
    if months:
        cleaned = tuple(m.strip() for m in months if m and str(m).strip())
        if not cleaned:
            raise ValueError("months list is empty")
        return PeriodSpec(
            label="Custom",
            kind="custom",
            year=None,
            months=cleaned,
        )
    raise ValueError("Provide quarter_label, or quarter+year, or months")


def available_quarter_labels(month_labels: Iterable[str]) -> List[str]:
    """
    Derive available ``Q# YYYY`` labels from ACTIVE reporting months.

    Sorted chronologically ascending.
    """
    seen: set[Tuple[int, int]] = set()
    for label in month_labels:
        parsed = parse_month_label(str(label))
        if not parsed:
            continue
        month, year = parsed
        seen.add((year, quarter_of_month(month)))
    ordered = sorted(seen, key=lambda t: (t[0], t[1]))
    return [f"Q{q} {y}" for y, q in ordered]
