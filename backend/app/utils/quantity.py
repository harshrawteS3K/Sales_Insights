"""Quantity parsing, formatting, and unit conversion helpers.

Canonical business unit for Sales Insights is **MT**.

Default ERP ingest treats Excel numbers as already-MT (no ÷1000).
``kg_to_mt`` / ``to_mt(..., source_unit=\"KG\")`` remain available only when a
workbook is explicitly known to be kilograms.
"""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Tuple, Union

_QTY_PATTERN = re.compile(r"[^0-9.\-]")

# 1 MT = 1000 KG (optional conversion only)
KG_PER_MT = Decimal("1000")
CANONICAL_UNIT = "MT"
DEFAULT_SOURCE_UNIT = "MT"


def normalize_unit(unit: Optional[str]) -> str:
    """Normalize unit labels to KG | MT | UNKNOWN."""
    raw = (unit or "").strip().upper()
    if raw in {"MT", "TON", "TONS", "TONNE", "TONNES", "METRIC TON", "METRIC TONNE"}:
        return "MT"
    if raw in {"KG", "KGS", "KILO", "KILOS", "KILOGRAM", "KILOGRAMS"}:
        return "KG"
    return raw or "UNKNOWN"


def kg_to_mt(value: Union[Decimal, float, int, str]) -> Decimal:
    """Convert kilograms to metric tonnes."""
    return (Decimal(str(value)) / KG_PER_MT).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )


def kg_to_mt_display(value: Union[Decimal, float, int, str, None]) -> float:
    """Stored kilograms to MT for analytics responses. Half-up, two decimal places."""
    return round_mt(kg_to_mt(value or 0))


def mt_to_kg(value: Union[Decimal, float, int, str]) -> Decimal:
    """Convert metric tonnes to kilograms."""
    return (Decimal(str(value)) * KG_PER_MT).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def to_mt(
    value: Union[Decimal, float, int, str],
    *,
    source_unit: str = DEFAULT_SOURCE_UNIT,
) -> Decimal:
    """
    Convert a quantity into canonical MT.

    - MT / unknown → unchanged (Excel values used as-is)
    - KG → ÷ 1000 (only when explicitly configured)
    """
    amount = Decimal(str(value))
    unit = normalize_unit(source_unit)
    if unit == "KG":
        return kg_to_mt(amount)
    return amount


def parse_quantity(raw: object) -> Tuple[Decimal, str]:
    """
    Parse a quantity cell into (numeric Decimal, display string).

    Accepts values like ``3,300``, ``3300``, ``3.300``, ``3,300.50``.
    Does **not** convert units — call ``to_mt`` separately for ERP ingest.
    """
    if raw is None:
        raise ValueError("Quantity is empty")

    if isinstance(raw, (int, float, Decimal)):
        value = Decimal(str(raw))
        display = format_quantity(value)
        return value, display

    text = str(raw).strip()
    if not text:
        raise ValueError("Quantity is empty")

    display = text
    normalized = text.replace(",", "")
    normalized = _QTY_PATTERN.sub("", normalized)
    if normalized in {"", "-", ".", "-."}:
        raise ValueError(f"Invalid quantity: {raw!r}")

    try:
        value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid quantity: {raw!r}") from exc

    return value, display


def parse_quantity_as_mt(
    raw: object,
    *,
    source_unit: str = DEFAULT_SOURCE_UNIT,
) -> Tuple[Decimal, str]:
    """Parse Excel quantity and convert to canonical MT."""
    value, _ = parse_quantity(raw)
    mt = to_mt(value, source_unit=source_unit)
    return mt, format_quantity(mt)


def parse_optional_stock(raw: object, *, field_label: str = "Stock") -> Optional[Decimal]:
    """
    Parse Opening/Closing Stock cell.

    - Blank / missing → ``None`` (allowed)
    - Numeric ≥ 0 → Decimal value
    - Negative or non-numeric text → ValueError
    """
    if raw is None:
        return None
    if isinstance(raw, float) and raw != raw:  # NaN
        return None
    if isinstance(raw, (int, float, Decimal)):
        value = Decimal(str(raw))
        if value < 0:
            raise ValueError(f"{field_label} must be zero or positive, got {raw!r}")
        return value

    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None

    normalized = text.replace(",", "")
    normalized = _QTY_PATTERN.sub("", normalized)
    if normalized in {"", ".", "-."}:
        raise ValueError(f"Invalid {field_label}: {raw!r}")
    if normalized == "-":
        return None

    try:
        value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {field_label}: {raw!r}") from exc

    if value < 0:
        raise ValueError(f"{field_label} must be zero or positive, got {raw!r}")
    return value


def format_quantity(value: Decimal | float | int) -> str:
    """Format a quantity with Indian-style thousand separators where practical."""
    number = Decimal(str(value))
    if number == number.to_integral_value():
        as_int = int(number)
        return f"{as_int:,}"
    # Keep up to 6 dp for MT converted from KG, trim trailing zeros
    return f"{number:,.6f}".rstrip("0").rstrip(".")


def quantity_as_mt(
    value: Union[Decimal, float, int, str],
    *,
    unit: Optional[str] = None,
    original_unit: Optional[str] = None,
) -> Decimal:
    """
    Canonical MT for analytics.

    Consolidation stores converted MT on ``quantity`` and sets ``unit`` to MT,
    keeping the workbook unit on ``original_unit``. Rows still marked KG
    (column default) hold kilograms and are divided by 1000 here.
    """
    amount = Decimal(str(value or 0))
    stored = normalize_unit(unit or "")
    source = normalize_unit(original_unit or "")
    if stored == "KG" or (stored != "MT" and source == "KG"):
        return kg_to_mt(amount)
    return amount


def format_mt(value: Union[Decimal, float, int, str]) -> str:
    """Display MT with exactly two decimal places (1.00, 12.40, 184.56)."""
    number = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{number:,.2f}"


def round_mt(value: Union[Decimal, float, int, str]) -> float:
    """Numeric MT rounded half-up to two decimal places."""
    number = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(number)


def safe_str(value: object, default: str = "") -> str:
    """Coerce a cell value to a trimmed string."""
    if value is None:
        return default
    text = str(value).strip()
    return text if text and text.lower() != "nan" else default


def optional_int(value: object) -> Optional[int]:
    """Parse an optional integer cell."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None
