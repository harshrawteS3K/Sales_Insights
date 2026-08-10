"""Shared calendar helpers for Quarterly period rollups.

APCOTEX business quarters (not calendar Jan–Mar):
  Q1 = April – June
  Q2 = July – September
  Q3 = October – December
  Q4 = January – March

``reports.reporting_month`` stores the period key (usually ``Q1 2026``).
Legacy month labels (``July 2026``) remain supported for historical data.
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

# APCOTEX quarters (Prompt 1A / Prompt 2)
_QUARTER_MONTHS = {
    1: (4, 5, 6),  # Apr–Jun
    2: (7, 8, 9),  # Jul–Sep
    3: (10, 11, 12),  # Oct–Dec
    4: (1, 2, 3),  # Jan–Mar
}

_QUARTER_LABEL_RE = re.compile(r"^\s*Q([1-4])\s+(\d{4})\s*$", re.IGNORECASE)
_MONTH_LABEL_RE = re.compile(
    r"^\s*(" + "|".join(_MONTH_NAMES) + r")\s+(\d{4})\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PeriodSpec:
    """Resolved set of period keys for a business quarter (quarter label + legacy months)."""

    label: str
    kind: str  # "quarter" | "year" | "half" | "custom" | "month"
    year: Optional[int]
    months: Tuple[str, ...]

    @property
    def month_list(self) -> List[str]:
        """Keys to match in ``reporting_month`` (includes ``Q# YYYY`` plus legacy months)."""
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
    """APCOTEX quarter 1–4 for a calendar month number."""
    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}")
    if month in (4, 5, 6):
        return 1
    if month in (7, 8, 9):
        return 2
    if month in (10, 11, 12):
        return 3
    return 4


def months_for_quarter(quarter: int, year: int) -> Tuple[str, ...]:
    """Legacy month labels covered by an APCOTEX quarter (same calendar year)."""
    q = int(quarter)
    if q not in _QUARTER_MONTHS:
        raise ValueError(f"Invalid quarter: {quarter}")
    return tuple(month_label(m, year) for m in _QUARTER_MONTHS[q])


def period_spec_for_quarter(quarter: int, year: int) -> PeriodSpec:
    """Build a PeriodSpec that matches ``Q# YYYY`` and legacy months for that quarter."""
    label = f"Q{int(quarter)} {int(year)}"
    legacy = months_for_quarter(quarter, year)
    return PeriodSpec(
        label=label,
        kind="quarter",
        year=int(year),
        months=(label,) + legacy,
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
    """Resolve a business period from any supported input shape."""
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


def available_quarter_labels(period_labels: Iterable[str]) -> List[str]:
    """
    Derive available ``Q# YYYY`` labels from ACTIVE period keys.

    Accepts stored quarter labels directly and derives quarters from legacy months.
    Sorted chronologically ascending.
    """
    seen: set[Tuple[int, int]] = set()
    for label in period_labels:
        text = str(label or "").strip()
        if not text:
            continue
        qmatch = _QUARTER_LABEL_RE.match(text)
        if qmatch:
            seen.add((int(qmatch.group(2)), int(qmatch.group(1))))
            continue
        parsed = parse_month_label(text)
        if not parsed:
            continue
        month, year = parsed
        seen.add((year, quarter_of_month(month)))
    ordered = sorted(seen, key=lambda t: (t[0], t[1]))
    return [f"Q{q} {y}" for y, q in ordered]


def quarter_sort_key(label: str) -> Optional[Tuple[int, int]]:
    """
    Chronological sort key for an APCOTEX period label.

    Returns ``(year, quarter)`` for ``Q# YYYY`` or legacy ``Month YYYY``.
    """
    text = str(label or "").strip()
    if not text:
        return None
    qmatch = _QUARTER_LABEL_RE.match(text)
    if qmatch:
        return (int(qmatch.group(2)), int(qmatch.group(1)))
    parsed = parse_month_label(text)
    if not parsed:
        return None
    month, year = parsed
    return (year, quarter_of_month(month))


def is_quarter_strictly_before(candidate: str, reference: str) -> bool:
    """True when ``candidate`` is chronologically before ``reference``."""
    left = quarter_sort_key(candidate)
    right = quarter_sort_key(reference)
    if left is None or right is None:
        return False
    return left < right


def previous_financial_quarter(label: str) -> Optional[str]:
    """
    Immediate previous APCOTEX quarter.

    ``Q1 2027`` → ``Q4 2026``; ``Q2 2026`` → ``Q1 2026``.
    """
    key = quarter_sort_key(label)
    if key is None:
        return None
    year, quarter = key
    if quarter <= 1:
        return f"Q4 {year - 1}"
    return f"Q{quarter - 1} {year}"
