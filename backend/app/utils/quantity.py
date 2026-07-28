"""Quantity parsing and formatting helpers."""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple


_QTY_PATTERN = re.compile(r"[^0-9.\-]")


def parse_quantity(raw: object) -> Tuple[Decimal, str]:
    """
    Parse a quantity cell into (numeric Decimal, display string).

    Accepts values like ``3,300``, ``3300``, ``3.300``, ``3,300.50``.
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
    return f"{number:,.3f}".rstrip("0").rstrip(".")


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
