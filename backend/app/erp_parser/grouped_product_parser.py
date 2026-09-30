"""Grouped product transaction layout.

A transaction header names Customer, Doc Date, and Quantity. Later rows are
``PRODUCT: <name>`` section markers. Transaction rows under a marker inherit
that product until the next marker. Section totals and the grand total are
not sales.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.utils.period_calendar import (
    fy_quarter_label,
    fy_start_for_calendar_month,
    month_label,
    quarter_of_month,
)
from app.utils.quantity import format_quantity, parse_quantity

_CUSTOMER_HEADERS = {"customer", "customer name"}
_DATE_HEADERS = {"doc date", "document date", "date", "doc. date"}
_PRODUCT_RE = re.compile(r"^product\s*:\s*(.+)$", re.IGNORECASE)
_TOTAL_RE = re.compile(r"^(grand\s+|sub\s+)?totals?\b", re.IGNORECASE)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _norm(value: Any) -> str:
    text = _cell(value).lower().replace("_", " ")
    text = re.sub(r"[^\w\s./()-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _header_norm(value: Any) -> str:
    text = _norm(value)
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_blank(row: Sequence[Any]) -> bool:
    return not any(_cell(cell) for cell in row)


def _is_total_label(value: Any) -> bool:
    text = _cell(value)
    return bool(text) and bool(_TOTAL_RE.match(text))


def _product_name(row: Sequence[Any]) -> Optional[str]:
    for cell in row:
        match = _PRODUCT_RE.match(_cell(cell))
        if match:
            name = match.group(1).strip()
            if name:
                return name
    return None


def _unit_from_header(header: str) -> str:
    upper = header.upper()
    if "KG" in upper or "KILO" in upper:
        return "KG"
    if re.search(r"\bMT\b|TONNE|TON\b", upper):
        return "MT"
    return "KG"


def _find_header(matrix: Sequence[Sequence[Any]]) -> Optional[Dict[str, Any]]:
    for index, row in enumerate(matrix[:80]):
        customer_col = date_col = qty_col = None
        qty_header = ""
        for col, cell in enumerate(row):
            plain = _header_norm(cell)
            raw = _norm(cell)
            if plain in _CUSTOMER_HEADERS or raw in _CUSTOMER_HEADERS:
                customer_col = col
            elif plain in _DATE_HEADERS or "doc date" in plain:
                date_col = col
            elif plain in {"quantity", "qty", "sales quantity", "sale quantity"} or raw.startswith(
                "quantity"
            ):
                qty_col = col
                qty_header = _cell(cell)
        if customer_col is None or date_col is None or qty_col is None:
            continue
        if len({customer_col, date_col, qty_col}) < 3:
            continue
        return {
            "header_index": index,
            "customer_col": customer_col,
            "date_col": date_col,
            "qty_col": qty_col,
            "unit": _unit_from_header(qty_header),
        }
    return None


def detect_grouped_product_layout(matrix: Sequence[Sequence[Any]]) -> bool:
    header = _find_header(matrix)
    if not header:
        return False
    start = int(header["header_index"]) + 1
    return any(_product_name(row) for row in matrix[start:])


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _cell(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    match = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", text)
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if month > 12 and day <= 12:
        day, month = month, day
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _at(row: Sequence[Any], index: int) -> Any:
    if index < 0 or index >= len(row):
        return None
    return row[index]


def extract_grouped_product_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract one sales row per transaction. Totals are ignored."""
    del fiscal_year_start, reporting_quarter
    empty: Dict[str, Any] = {
        "rows": [],
        "header_row": 1,
        "layout": "grouped_product_transactions",
        "score": 0,
        "confidence": 0,
        "llm_used": False,
        "products_detected": 0,
        "quantity_ok": 0,
        "quantity_fail": 0,
        "skipped_invalid": 0,
        "unit": "KG",
    }
    header = _find_header(matrix)
    if not header or not detect_grouped_product_layout(matrix):
        return empty

    customer_col = int(header["customer_col"])
    date_col = int(header["date_col"])
    qty_col = int(header["qty_col"])
    unit = str(header["unit"])
    current_product: Optional[str] = None
    products: List[str] = []
    rows: List[Dict[str, Any]] = []
    skipped = 0

    for row in matrix[int(header["header_index"]) + 1 :]:
        if _is_blank(row):
            continue
        product = _product_name(row)
        if product:
            current_product = product
            if product not in products:
                products.append(product)
            continue
        if any(_is_total_label(cell) for cell in row):
            continue
        if not current_product:
            continue
        customer = _cell(_at(row, customer_col))
        if not customer or _is_total_label(customer) or _PRODUCT_RE.match(customer):
            continue
        parsed_date = _parse_date(_at(row, date_col))
        if parsed_date is None:
            skipped += 1
            continue
        try:
            qty, qty_display = parse_quantity(_at(row, qty_col))
        except ValueError:
            skipped += 1
            continue
        if qty <= 0:
            continue
        fy_start = fy_start_for_calendar_month(parsed_date.month, parsed_date.year)
        quarter = quarter_of_month(parsed_date.month)
        period = fy_quarter_label(fy_start, quarter)
        rows.append(
            {
                "customer_name": customer,
                "product": current_product,
                "sales_quantity": qty,
                "sales_quantity_display": qty_display or format_quantity(qty),
                "period": period,
                "reporting_quarter": period,
                "source_month": month_label(parsed_date.month, parsed_date.year),
                "transaction_date": parsed_date.isoformat(),
                "original_unit": unit,
                "unit": unit,
            }
        )

    return {
        "rows": rows,
        "header_row": int(header["header_index"]) + 1,
        "layout": "grouped_product_transactions",
        "score": 98 if rows else 0,
        "confidence": 98 if rows else 0,
        "llm_used": False,
        "products_detected": len(products),
        "quantity_ok": len(rows),
        "quantity_fail": 0,
        "skipped_invalid": skipped,
        "unit": unit,
    }
