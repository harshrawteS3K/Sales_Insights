"""Detect product×month cross-tab ERP layouts (e.g. EAST ARIEN IMPEX).

Layout example::

    Row N:     | APCOFLEX N1110 |     |     | APCOFLEX N745 | ...
    Row N+1:   PARTICULARS | Apr | May | Jun | Apr | May | Jun | TOTAL QTY
    Row N+2+:  Customer    |  qty values under each product's months

Customer is the row label; products are column groups; months are sub-headers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.erp_parser.header_mapper import (
    NOISE_HEADERS,
    best_field_match,
    is_month_header,
    normalize_header_text,
)

# Labels that sit in the customer/stub column of a cross-tab
_STUB_CUSTOMER = {
    "particulars",
    "particular",
    "customer",
    "customer name",
    "party",
    "party name",
    "buyer",
    "account name",
    "name",
    "dealer",
    "dealer name",
}

_TOTAL_LIKE = {
    "total",
    "total qty",
    "total quantity",
    "grand total",
    "qty total",
    "net total",
}


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_total_header(norm: str) -> bool:
    if not norm:
        return False
    if norm in _TOTAL_LIKE:
        return True
    return norm.startswith("total") and "qty" in norm


def _looks_like_product_label(raw: Any) -> bool:
    text = _cell(raw)
    if not text or len(text) < 2:
        return False
    norm = normalize_header_text(text)
    if not norm or norm in NOISE_HEADERS or norm in _STUB_CUSTOMER:
        return False
    if is_month_header(norm) or _is_total_header(norm):
        return False
    # Month-year like "Jun - 2026" already caught by is_month_header
    if norm in {"qty", "quantity", "sales quantity"}:
        return False
    return True


def detect_product_month_matrix(
    matrix: Sequence[Sequence[Any]],
    *,
    scan_rows: int = 20,
) -> Optional[Dict[str, Any]]:
    """
    Find a product-band row + month-band row forming a cross-tab.

    Returns ``None`` when the sheet is not this layout.
    """
    limit = min(scan_rows, max(0, len(matrix) - 1))
    best: Optional[Dict[str, Any]] = None
    best_score = 0.0

    for prod_idx in range(limit):
        month_idx = prod_idx + 1
        if month_idx >= len(matrix):
            break
        prod_row = list(matrix[prod_idx])
        month_row = list(matrix[month_idx])
        width = max(len(prod_row), len(month_row))
        if width < 4:
            continue

        # Stub / customer header on month row
        stub = normalize_header_text(month_row[0] if month_row else "")
        stub_ok = stub in _STUB_CUSTOMER or best_field_match(stub, "customer")[1] >= 85
        if not stub_ok:
            # Sometimes stub is blank and customer header is elsewhere — require
            # at least a clear customer synonym somewhere in first 3 cells
            stub_ok = any(
                normalize_header_text(month_row[c] if c < len(month_row) else "") in _STUB_CUSTOMER
                for c in range(min(3, width))
            )
        if not stub_ok:
            continue

        month_cols: List[Tuple[int, str, str]] = []
        for c in range(width):
            raw = month_row[c] if c < len(month_row) else None
            norm = normalize_header_text(raw)
            if is_month_header(norm):
                label = _cell(raw) or norm
                key = norm
                # strip year suffix for quarter map
                import re

                key = re.sub(r"[\s\-_/']*\d{2,4}$", "", norm).strip() or norm
                month_cols.append((c, label, key))

        if len(month_cols) < 2:
            continue

        # Product anchors on the row above (non-month, non-total cells).
        # Merged cells are unwrapped into every covered column — collapse runs.
        product_anchors: List[Tuple[int, str]] = []
        prev_label: Optional[str] = None
        for c in range(width):
            raw = prod_row[c] if c < len(prod_row) else None
            if not _looks_like_product_label(raw):
                prev_label = None
                continue
            text = _cell(raw)
            if text == prev_label:
                continue
            product_anchors.append((c, text))
            prev_label = text

        if len(product_anchors) < 2:
            continue

        # Build groups: product at col P owns following month columns until next product / total
        product_anchors.sort(key=lambda t: t[0])
        total_cols = {
            c
            for c in range(width)
            if _is_total_header(normalize_header_text(month_row[c] if c < len(month_row) else None))
        }

        groups: List[Dict[str, Any]] = []
        for i, (start, pname) in enumerate(product_anchors):
            end = product_anchors[i + 1][0] if i + 1 < len(product_anchors) else width
            owned_months: List[Tuple[int, str, str]] = []
            for col, label, key in month_cols:
                if start <= col < end and col not in total_cols:
                    owned_months.append((col, label, key))
            if owned_months:
                groups.append(
                    {
                        "product": pname,
                        "start_col": start,
                        "month_columns": owned_months,
                    }
                )

        if len(groups) < 2:
            continue

        # Customer column = stub column (usually 0)
        customer_col = 0
        for c in range(min(3, width)):
            if normalize_header_text(month_row[c] if c < len(month_row) else "") in _STUB_CUSTOMER:
                customer_col = c
                break

        score = 40.0 + min(30.0, len(groups) * 5.0) + min(20.0, len(month_cols) * 2.0)
        if score > best_score:
            best_score = score
            best = {
                "layout": "product_month_matrix",
                "product_row_index": prod_idx,
                "header_row_index": month_idx,
                "header_row": month_idx + 1,
                "customer_col": customer_col,
                "groups": groups,
                "score": round(score, 2),
                "month_column_meta": [
                    {"column": c, "header": lab, "month": key}
                    for g in groups
                    for c, lab, key in g["month_columns"]
                ],
            }

    return best


def extract_product_month_matrix_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    layout: Dict[str, Any],
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Expand product×month cross-tab into Customer / Product / Qty rows.

    Each month column stays its own row. ``period`` is the FY quarter.
    ``source_month`` keeps the calendar month for the sales trend chart.
    Quantities are taken exactly as written in Excel (no unit conversion).
    """
    from decimal import Decimal

    from app.erp_parser.fiscal_quarters import (
        month_key_to_quarter,
        quarter_label,
        resolve_fy_start_year,
        source_month_label,
    )
    from app.utils.quantity import format_quantity, parse_quantity

    def _is_blank_row(row: Sequence[Any]) -> bool:
        return not any(_cell(c) for c in row)

    def _is_total_row(row: Sequence[Any]) -> bool:
        import re

        total_re = re.compile(
            r"^\s*(grand\s*)?total\b|\bsub\s*total\b|\btotals?\b",
            flags=re.IGNORECASE,
        )
        for cell in row:
            text = _cell(cell)
            if text and total_re.search(text):
                return True
        return False

    header_idx = int(layout["header_row_index"])
    customer_col = int(layout["customer_col"])
    groups = list(layout.get("groups") or [])
    fy_start = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )

    rows: List[Dict[str, Any]] = []
    skipped_total = 0
    skipped_blank = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0
    errors: List[str] = []

    def _at(row: Sequence[Any], idx: int) -> Any:
        return row[idx] if idx < len(row) else None

    for abs_idx, row in enumerate(matrix[header_idx + 1 :], start=header_idx + 2):
        if _is_blank_row(row):
            skipped_blank += 1
            continue
        if _is_total_row(row):
            skipped_total += 1
            continue

        customer = _cell(_at(row, customer_col))
        if not customer:
            skipped_blank += 1
            continue

        emitted = 0
        for group in groups:
            product = str(group.get("product") or "").strip()
            if not product:
                continue
            month_meta = [
                (int(c), str(lab), str(key))
                for c, lab, key in (group.get("month_columns") or [])
            ]

            emitted_month = False
            for col, lab, key in month_meta:
                q_num = month_key_to_quarter(key)
                raw = _at(row, col)
                if raw is None or _cell(raw) == "":
                    continue
                try:
                    total, _ = parse_quantity(raw)
                except ValueError:
                    continue
                if total == 0:
                    continue
                if total < 0:
                    skipped_invalid += 1
                    errors.append(f"Row {abs_idx}: negative quantity for {product}")
                    continue
                if q_num:
                    period = quarter_label(fy_start, q_num)
                else:
                    period = (reporting_quarter or "").strip()
                payload: Dict[str, Any] = {
                    "customer_name": customer,
                    "product": product,
                    "sales_quantity": total,
                    "sales_quantity_display": format_quantity(total),
                }
                src = source_month_label(key, fy_start, lab) if q_num else None
                if src:
                    payload["source_month"] = src
                if period:
                    payload["period"] = period
                    payload["reporting_quarter"] = period
                rows.append(payload)
                qty_ok += 1
                emitted += 1
                emitted_month = True
            if not emitted_month:
                continue

        if emitted == 0:
            skipped_blank += 1

    return {
        "rows": rows,
        "skipped_total": skipped_total,
        "skipped_blank": skipped_blank,
        "skipped_invalid": skipped_invalid,
        "quantity_ok": qty_ok,
        "quantity_fail": qty_fail,
        "errors": errors[:50],
        "fiscal_year_start": fy_start,
        "monthly_pivot": True,
        "layout": "product_month_matrix",
    }
