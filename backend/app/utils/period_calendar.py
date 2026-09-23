"""Indian Financial Year (Apr–Mar) period helpers.

Canonical quarter label: ``FY 2025-26 • Q1``
Display label:           ``FY 2025–26 • Q1 (Apr–Jun)``

| Display             | Months              |
| ------------------- | ------------------- |
| FY 2025–26 • Q1     | Apr 2025 – Jun 2025 |
| FY 2025–26 • Q2     | Jul 2025 – Sep 2025 |
| FY 2025–26 • Q3     | Oct 2025 – Dec 2025 |
| FY 2025–26 • Q4     | Jan 2026 – Mar 2026 |

Legacy stored keys ``Q1 2025`` (FY-start year) and month labels remain matchable.
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

# Quarter → (calendar months). Q4 months use fy_start + 1.
_QUARTER_MONTHS = {
    1: (4, 5, 6),
    2: (7, 8, 9),
    3: (10, 11, 12),
    4: (1, 2, 3),
}

_QUARTER_RANGE = {
    1: "Apr–Jun",
    2: "Jul–Sep",
    3: "Oct–Dec",
    4: "Jan–Mar",
}

# FY 2025-26 • Q1  |  FY 2025–26 • Q1  |  FY 2025-26 Q1
_FY_QUARTER_RE = re.compile(
    r"^\s*FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*[•·.\-]?\s*Q\s*([1-4])\s*$",
    re.IGNORECASE,
)
# FY 2025-26 (annual)
_FY_ANNUAL_RE = re.compile(
    r"^\s*FY\s*(\d{4})\s*[-–—/]\s*(\d{2}|\d{4})\s*$",
    re.IGNORECASE,
)
# Legacy: Q1 2025 (year = FY start)
_LEGACY_Q_RE = re.compile(r"^\s*Q([1-4])\s+(\d{4})\s*$", re.IGNORECASE)
_MONTH_LABEL_RE = re.compile(
    r"^\s*(" + "|".join(_MONTH_NAMES) + r")\s+(\d{4})\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PeriodSpec:
    """Resolved financial period with all matchable reporting keys."""

    label: str  # canonical FY quarter or annual
    kind: str  # "quarter" | "year" | "half" | "custom" | "month"
    year: Optional[int]  # FY start year when known
    months: Tuple[str, ...]
    quarter: Optional[int] = None

    @property
    def month_list(self) -> List[str]:
        return list(self.months)

    @property
    def display(self) -> str:
        return format_period_display(self.label)


def month_label(month: int, year: int) -> str:
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


def fy_end_yy(fy_start: int) -> str:
    return f"{(int(fy_start) + 1) % 100:02d}"


def fy_short(fy_start: int) -> str:
    """``FY 2025-26`` (ASCII hyphen for storage)."""
    return f"FY {int(fy_start)}-{fy_end_yy(fy_start)}"


def fy_short_display(fy_start: int) -> str:
    """``FY 2025–26`` (en-dash for UI)."""
    return f"FY {int(fy_start)}–{fy_end_yy(fy_start)}"


def fy_quarter_label(fy_start: int, quarter: int) -> str:
    """Canonical storage label: ``FY 2025-26 • Q1``."""
    q = int(quarter)
    if q not in (1, 2, 3, 4):
        raise ValueError(f"Invalid quarter: {quarter}")
    return f"{fy_short(fy_start)} • Q{q}"


def fy_annual_label(fy_start: int) -> str:
    return fy_short(fy_start)


def format_period_display(label: Optional[str]) -> str:
    """
    UI display for any known period key.

    ``FY 2025-26 • Q1`` → ``FY 2025–26 • Q1 (Apr–Jun)``
    ``FY 2025-26`` → ``FY 2025–26``
    Legacy ``Q1 2025`` → same FY display.
    """
    spec = parse_quarter_label(label or "")
    if not spec:
        return (label or "").strip()
    if spec.kind == "year" and spec.year is not None:
        return fy_short_display(spec.year)
    if spec.kind == "quarter" and spec.year is not None and spec.quarter:
        return f"{fy_short_display(spec.year)} • Q{spec.quarter}"
    return spec.label


def quarter_of_month(month: int) -> int:
    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}")
    if month in (4, 5, 6):
        return 1
    if month in (7, 8, 9):
        return 2
    if month in (10, 11, 12):
        return 3
    return 4


def fy_start_for_calendar_month(month: int, year: int) -> int:
    """Apr 2025 → 2025; Jan 2026 → 2025."""
    return int(year) if int(month) >= 4 else int(year) - 1


def calendar_year_for_fy_month(fy_start: int, month: int) -> int:
    """Month number within an FY → calendar year."""
    return int(fy_start) + 1 if int(month) <= 3 else int(fy_start)


def months_for_fy_quarter(fy_start: int, quarter: int) -> Tuple[str, ...]:
    q = int(quarter)
    if q not in _QUARTER_MONTHS:
        raise ValueError(f"Invalid quarter: {quarter}")
    out = []
    for m in _QUARTER_MONTHS[q]:
        out.append(month_label(m, calendar_year_for_fy_month(fy_start, m)))
    return tuple(out)


def period_spec_for_quarter(fy_start: int, quarter: int) -> PeriodSpec:
    """Build PeriodSpec for an Indian FY quarter."""
    fy_start = int(fy_start)
    q = int(quarter)
    canonical = fy_quarter_label(fy_start, q)
    legacy_q = f"Q{q} {fy_start}"
    legacy_months = months_for_fy_quarter(fy_start, q)
    # Also accept display variant with en-dash
    display_key = f"{fy_short_display(fy_start)} • Q{q}"
    months = (canonical, display_key, legacy_q) + legacy_months
    return PeriodSpec(
        label=canonical,
        kind="quarter",
        year=fy_start,
        months=tuple(dict.fromkeys(months)),
        quarter=q,
    )


def period_spec_for_fy_year(fy_start: int) -> PeriodSpec:
    fy_start = int(fy_start)
    canonical = fy_annual_label(fy_start)
    display_key = fy_short_display(fy_start)
    keys: List[str] = [canonical, display_key]
    for q in (1, 2, 3, 4):
        keys.extend(period_spec_for_quarter(fy_start, q).month_list)
    return PeriodSpec(
        label=canonical,
        kind="year",
        year=fy_start,
        months=tuple(dict.fromkeys(keys)),
        quarter=None,
    )


def _normalize_fy_end(start: int, end_raw: str) -> bool:
    """Validate FY end token matches start+1 (``26`` or ``2026``)."""
    end_raw = (end_raw or "").strip()
    expected_yy = fy_end_yy(start)
    if len(end_raw) == 2:
        return end_raw == expected_yy
    if len(end_raw) == 4 and end_raw.isdigit():
        return int(end_raw) == start + 1
    return False


def parse_quarter_label(label: str) -> Optional[PeriodSpec]:
    """
    Parse FY quarter / annual / legacy ``Q# YYYY`` / month labels into PeriodSpec.
    """
    if not label:
        return None
    text = re.sub(r"\s+", " ", str(label).strip())
    # Strip trailing range in parens for display forms
    text = re.sub(r"\s*\((?:Apr|Jul|Oct|Jan)[^)]*\)\s*$", "", text, flags=re.IGNORECASE).strip()

    m = _FY_QUARTER_RE.match(text)
    if m:
        fy_start = int(m.group(1))
        if not _normalize_fy_end(fy_start, m.group(2)):
            return None
        return period_spec_for_quarter(fy_start, int(m.group(3)))

    m = _FY_ANNUAL_RE.match(text)
    if m:
        fy_start = int(m.group(1))
        if not _normalize_fy_end(fy_start, m.group(2)):
            return None
        return period_spec_for_fy_year(fy_start)

    m = _LEGACY_Q_RE.match(text)
    if m:
        # Treat year as FY start (aligned with fiscal_quarters.quarter_label)
        return period_spec_for_quarter(int(m.group(2)), int(m.group(1)))

    parsed = parse_month_label(text)
    if parsed:
        month, year = parsed
        fy_start = fy_start_for_calendar_month(month, year)
        q = quarter_of_month(month)
        return period_spec_for_quarter(fy_start, q)

    return None


def resolve_period(
    *,
    quarter: Optional[int] = None,
    year: Optional[int] = None,
    quarter_label: Optional[str] = None,
    months: Optional[Sequence[str]] = None,
) -> PeriodSpec:
    if quarter_label:
        spec = parse_quarter_label(quarter_label)
        if spec:
            return spec
        raise ValueError(f"Invalid quarter label: {quarter_label!r}")
    if quarter is not None and year is not None:
        return period_spec_for_quarter(int(year), int(quarter))
    if months:
        cleaned = tuple(m.strip() for m in months if m and str(m).strip())
        if not cleaned:
            raise ValueError("months list is empty")
        return PeriodSpec(label="Custom", kind="custom", year=None, months=cleaned)
    raise ValueError("Provide quarter_label, or quarter+year, or months")


def available_quarter_labels(period_labels: Iterable[str]) -> List[str]:
    """Derive canonical FY quarter labels from stored period keys."""
    seen: set[Tuple[int, int]] = set()
    for label in period_labels:
        spec = parse_quarter_label(str(label or "").strip())
        if not spec or spec.year is None:
            continue
        if spec.kind == "year":
            for q in (1, 2, 3, 4):
                seen.add((spec.year, q))
        elif spec.quarter:
            seen.add((spec.year, spec.quarter))
    ordered = sorted(seen, key=lambda t: (t[0], t[1]))
    return [fy_quarter_label(y, q) for y, q in ordered]


def quarter_sort_key(label: str) -> Optional[Tuple[int, int]]:
    """Chronological sort key ``(fy_start, quarter)``; annual → quarter 0."""
    spec = parse_quarter_label(label)
    if not spec or spec.year is None:
        return None
    if spec.kind == "year":
        return (spec.year, 0)
    return (spec.year, int(spec.quarter or 0))


def is_quarter_strictly_before(candidate: str, reference: str) -> bool:
    left = quarter_sort_key(candidate)
    right = quarter_sort_key(reference)
    if left is None or right is None:
        return False
    return left < right


def previous_financial_quarter(label: str) -> Optional[str]:
    """``FY 2025-26 • Q1`` → ``FY 2024-25 • Q4``."""
    key = quarter_sort_key(label)
    if key is None:
        return None
    year, quarter = key
    if quarter <= 0:
        return fy_quarter_label(year - 1, 4)
    if quarter <= 1:
        return fy_quarter_label(year - 1, 4)
    return fy_quarter_label(year, quarter - 1)
