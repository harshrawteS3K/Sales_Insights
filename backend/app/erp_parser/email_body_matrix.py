"""Email-body sales matrix: product banners, month columns, customer quantities.

Runs only on the sheet produced by the email body adapter. Zero cells are
kept. Blank separator rows are ignored. A new product banner switches context.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.erp_parser.documents.email_body import LLM_MARK, SHEET_NAME
from app.erp_parser.fiscal_quarters import (
    month_number_from_key,
    quarter_label,
    resolve_fy_start_year,
)
from app.erp_parser.header_dictionary import normalize_header_text
from app.erp_parser.header_mapper import detect_month_columns, is_month_header
from app.utils.period_calendar import (
    calendar_year_for_fy_month,
    fy_start_for_calendar_month,
    month_label,
    quarter_of_month,
)
from app.utils.quantity import parse_quantity

_MS_RE = re.compile(r"^(?:m\s*/\s*s\.?|messrs\.?)\s+", re.IGNORECASE)
_TOTAL_RE = re.compile(r"^(grand\s+)?total\b", re.IGNORECASE)


def extract_email_body_matrix_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    sheet_name: str = "",
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    distributor_label: str = "",
) -> Optional[Dict[str, Any]]:
    if (sheet_name or "").strip().casefold() != SHEET_NAME.casefold():
        return None
    if not matrix:
        return None
    header_idx, months = _find_header(matrix)
    if header_idx < 0 or len(months) < 2:
        return None
    month_cols = {col for col, _label, _key in months}
    fallback_fy = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )
    product = ""
    products: List[str] = []
    customers: List[str] = []
    rows: List[Dict[str, Any]] = []
    for raw in matrix[header_idx + 1 :]:
        if _is_month_header_row(raw, month_cols):
            continue
        label = _label_cell(raw, month_cols)
        if not label or label == LLM_MARK or _TOTAL_RE.match(label):
            continue
        quantities = _month_quantities(raw, months)
        if quantities is None:
            if label not in products:
                products.append(label)
            product = label
            continue
        if not product:
            continue
        customer = _customer_name(label)
        if not customer or customer.casefold() == product.casefold():
            continue
        if customer not in customers:
            customers.append(customer)
        for col, month_label_text, month_key, qty, qty_display in quantities:
            del col
            period, source_month = _period_for_month(month_key, month_label_text, fallback_fy)
            if not period:
                continue
            rows.append(
                {
                    "customer_name": customer,
                    "product": product,
                    "sales_quantity": qty,
                    "sales_quantity_display": qty_display,
                    "period": period,
                    "reporting_quarter": period,
                    "source_month": source_month,
                    "original_unit": "KG",
                }
            )
    if not rows or not products or not customers:
        return None
    llm_used = any(str(cell).strip() == LLM_MARK for row in matrix for cell in row)
    periods = [str(row.get("period") or "") for row in rows if row.get("period")]
    quarter = ""
    if periods:
        dominant = max(set(periods), key=periods.count)
        match = re.search(r"Q\s*([1-4])", dominant, re.IGNORECASE)
        quarter = f"Q{match.group(1)}" if match else dominant
    return {
        "rows": rows,
        "layout": "email_matrix",
        "score": 90 if llm_used else 98,
        "llm_used": llm_used,
        "header_row": header_idx + 1,
        "distributor": distributor_label,
        "products": products,
        "products_detected": len(products),
        "customers_detected": len(customers),
        "quarter": quarter,
        "fiscal_year_start": fallback_fy,
        "monthly_pivot": True,
        "quantity_ok": len(rows),
        "quantity_fail": 0,
        "skipped_invalid": 0,
    }


def _find_header(matrix: Sequence[Sequence[Any]]) -> Tuple[int, List[Tuple[int, str, str]]]:
    limit = min(20, len(matrix))
    for idx in range(limit):
        months = detect_month_columns(list(matrix[idx]))
        if len(months) >= 2:
            return idx, months
    return -1, []


def _is_month_header_row(row: Sequence[Any], month_cols: set) -> bool:
    hits = 0
    for col in month_cols:
        if col < len(row) and is_month_header(normalize_header_text(row[col])):
            hits += 1
    return hits >= 2


def _label_cell(row: Sequence[Any], month_cols: set) -> str:
    for idx, value in enumerate(row):
        if idx in month_cols:
            continue
        text = _text(value)
        if text:
            return text
    return ""


def _month_quantities(
    row: Sequence[Any],
    months: Sequence[Tuple[int, str, str]],
) -> Optional[List[Tuple[int, str, str, Decimal, str]]]:
    """Numeric month cells, including zero. None when the row is not a customer row."""
    found: List[Tuple[int, str, str, Decimal, str]] = []
    saw_number = False
    for col, label, key in months:
        value = row[col] if col < len(row) else None
        if value is None or _text(value) == "":
            continue
        try:
            qty, display = parse_quantity(value)
        except (ValueError, ArithmeticError):
            return None
        if qty < 0:
            return None
        saw_number = True
        found.append((col, label, key, qty, display))
    if not saw_number:
        return None
    return found


def _period_for_month(month_key: str, header: str, fallback_fy: int) -> Tuple[str, Optional[str]]:
    month_num = month_number_from_key(month_key)
    if not month_num:
        return "", None
    year_match = re.search(r"(20\d{2})", header or "")
    if year_match:
        year = int(year_match.group(1))
        fy = fy_start_for_calendar_month(month_num, year)
        source = month_label(month_num, year)
    else:
        fy = fallback_fy
        source = month_label(month_num, calendar_year_for_fy_month(fy, month_num))
    return quarter_label(fy, quarter_of_month(month_num)), source


def _customer_name(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw).strip()
    text = _MS_RE.sub("", text).strip()
    letters = [char for char in text if char.isalpha()]
    if letters and sum(1 for char in letters if char.isupper()) / len(letters) >= 0.8:
        return text.title()
    return text


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
