"""Extract and normalize ERP sales rows after the header."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.erp_parser.fiscal_quarters import (
    group_month_indexes_by_quarter,
    quarter_label,
    resolve_fy_start_year,
)
from app.utils.quantity import format_quantity, parse_quantity

_TOTAL_RE = re.compile(
    r"^\s*(grand\s*)?total\b|\bsub\s*total\b|\btotals?\b",
    flags=re.IGNORECASE,
)


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_total_row(row: Sequence[Any]) -> bool:
    for cell in row:
        text = _cell_str(cell)
        if text and _TOTAL_RE.search(text):
            return True
    return False


def _is_blank_row(row: Sequence[Any]) -> bool:
    return not any(_cell_str(c) for c in row)


def _sum_quantity_columns(row: Sequence[Any], columns: Sequence[int]) -> tuple[Decimal, str, bool]:
    """Sum numeric values across month/qty columns (Excel values as-is)."""
    total = Decimal("0")
    any_parsed = False
    for idx in columns:
        raw = row[idx] if idx < len(row) else None
        if raw is None or _cell_str(raw) == "":
            continue
        try:
            qty_val, _disp = parse_quantity(raw)
        except ValueError:
            continue
        total += qty_val
        any_parsed = True
    display = format_quantity(total) if any_parsed else "0"
    return total, display, any_parsed


def extract_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    header_row_index: int,
    positions: Dict[str, Optional[int]],
    quantity_columns: Optional[Sequence[int]] = None,
    month_column_meta: Optional[Sequence[Dict[str, Any]]] = None,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    source_quantity_unit: Optional[str] = None,  # API compat; ignored (no conversion)
) -> Dict[str, Any]:
    """
    Extract valid data rows after the header.

    Monthly-pivot workbooks (Apr…Mar columns) are expanded into **quarterly**
    sales rows (Q1–Q4 of the fiscal year), not a single annual total.

    Quantities are stored exactly as written in Excel (no unit conversion).
    """
    _ = source_quantity_unit
    cust_i = positions.get("customer")
    prod_i = positions.get("product")
    qty_i = positions.get("quantity")
    qty_cols = list(quantity_columns or [])

    month_meta: List[Tuple[int, str, str]] = []
    for item in month_column_meta or []:
        try:
            month_meta.append(
                (int(item["column"]), str(item.get("header") or ""), str(item.get("month") or ""))
            )
        except (KeyError, TypeError, ValueError):
            continue

    by_quarter = group_month_indexes_by_quarter(month_meta) if month_meta else {}
    fy_start = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )
    monthly_mode = bool(qty_cols) and bool(by_quarter)

    rows: List[Dict[str, Any]] = []
    skipped_total = 0
    skipped_blank = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0

    if cust_i is None or prod_i is None or (qty_i is None and not qty_cols):
        return {
            "rows": [],
            "skipped_total": 0,
            "skipped_blank": 0,
            "skipped_invalid": 0,
            "quantity_ok": 0,
            "quantity_fail": 0,
            "errors": ["Missing required column mapping (customer, product, quantity)"],
            "fiscal_year_start": fy_start,
            "monthly_pivot": False,
        }

    errors: List[str] = []
    for abs_idx, row in enumerate(matrix[header_row_index + 1 :], start=header_row_index + 2):
        if _is_blank_row(row):
            skipped_blank += 1
            continue
        if _is_total_row(row):
            skipped_total += 1
            continue

        def _at(idx: int) -> Any:
            return row[idx] if idx < len(row) else None

        customer = _cell_str(_at(cust_i))
        product = _cell_str(_at(prod_i))

        if not customer and not product:
            skipped_blank += 1
            continue

        if not customer or not product:
            skipped_invalid += 1
            errors.append(f"Row {abs_idx}: missing customer or product")
            continue

        if monthly_mode:
            emitted = 0
            for q_num, cols in sorted(by_quarter.items()):
                qty_val, qty_display, any_parsed = _sum_quantity_columns(row, cols)
                if not any_parsed or qty_val == 0:
                    continue
                if qty_val < 0:
                    skipped_invalid += 1
                    errors.append(f"Row {abs_idx}: negative quantity in Q{q_num}")
                    continue
                period = quarter_label(fy_start, q_num)
                rows.append(
                    {
                        "customer_name": customer,
                        "product": product,
                        "sales_quantity": qty_val,
                        "sales_quantity_display": qty_display,
                        "period": period,
                        "reporting_quarter": period,
                    }
                )
                qty_ok += 1
                emitted += 1
            if emitted == 0:
                skipped_blank += 1
            continue

        if qty_cols:
            qty_val, qty_display, any_parsed = _sum_quantity_columns(row, qty_cols)
            if not any_parsed or qty_val == 0:
                skipped_blank += 1
                continue
            qty_ok += 1
        else:
            qty_cell = _at(qty_i) if qty_i is not None else None
            try:
                qty_val, qty_display = parse_quantity(qty_cell)
                qty_ok += 1
            except ValueError as exc:
                qty_fail += 1
                skipped_invalid += 1
                errors.append(f"Row {abs_idx}: {exc}")
                continue

        if qty_val < 0:
            skipped_invalid += 1
            errors.append(f"Row {abs_idx}: negative quantity")
            continue

        rows.append(
            {
                "customer_name": customer,
                "product": product,
                "sales_quantity": qty_val,
                "sales_quantity_display": qty_display,
            }
        )

    return {
        "rows": rows,
        "skipped_total": skipped_total,
        "skipped_blank": skipped_blank,
        "skipped_invalid": skipped_invalid,
        "quantity_ok": qty_ok,
        "quantity_fail": qty_fail,
        "errors": errors[:50],
        "fiscal_year_start": fy_start,
        "monthly_pivot": monthly_mode,
    }
