"""Cross-product matrix ERP layout (Puneet Dyes and the same grid).

Customer names stay in the left-most text column. Month headers repeat once
per product. The product name sits on the row above or below those months.
Total columns separate product blocks and are ignored.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.erp_parser.fiscal_quarters import month_number_from_key, quarter_label, resolve_fy_start_year
from app.erp_parser.matrix_month_parser import _month_spec
from app.utils.period_calendar import fy_short, fy_start_for_calendar_month, month_label, parse_quarter_label
from app.utils.quantity import format_quantity, parse_quantity

_HEADER_WORDS = {
    "customer",
    "customer name",
    "party",
    "party name",
    "particulars",
    "particular",
    "buyer",
    "product",
    "product name",
    "item",
    "item name",
    "sr",
    "sr no",
    "s no",
    "s.no",
}
_SKIP_ROW = re.compile(
    r"^(grand\s+total|sub\s*total|subtotal|total|opening(?:\s+balance)?|closing(?:\s+balance)?|balance|summary)\b",
    re.IGNORECASE,
)
_TOTAL = re.compile(r"^(grand\s+total|sub\s*total|subtotal|totals?(?:\s+qty|\s+quantity)?)\b", re.IGNORECASE)
_KEYWORD_PRODUCT = re.compile(
    r"(?i)\b(?:APCOTEX|APCOFLEX|NBR|SBR|NVC|PB|CB|SR)\b"
)
_CODE_PRODUCT = re.compile(
    r"(?i)\b(?:NBR|SBR|NVC|PB|CB|SR|N|P)\s*[-]?\s*[A-Z]*\d[A-Z0-9-]*\b"
)

MonthCol = Tuple[int, str, str, Optional[int]]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _is_total(text: str) -> bool:
    return bool(text) and bool(_TOTAL.match(text.strip()))


def _is_product_text(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 2 or _is_total(cleaned):
        return False
    if _month_spec(cleaned):
        return False
    if cleaned.casefold() in _HEADER_WORDS:
        return False
    return bool(_KEYWORD_PRODUCT.search(cleaned) or _CODE_PRODUCT.search(cleaned))


def _month_columns(row: Sequence[Any]) -> List[MonthCol]:
    found: List[MonthCol] = []
    for idx, raw in enumerate(row):
        spec = _month_spec(raw)
        if not spec:
            continue
        key, label, year = spec
        found.append((idx, key, label, year))
    return found


def _labels_for_months(row: Sequence[Any], months: Sequence[MonthCol]) -> List[str]:
    labels: List[str] = []
    for col, _key, _label, _year in months:
        text = _cell(row[col] if col < len(row) else None)
        if _is_product_text(text):
            labels.append(text)
    return labels


def _crossed_total(row: Sequence[Any], start: int, end: int) -> bool:
    for col in range(start + 1, end):
        if col < len(row) and _is_total(_cell(row[col])):
            return True
    return False


def _build_groups(
    product_row: Sequence[Any],
    month_row: Sequence[Any],
    months: Sequence[MonthCol],
) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    previous_col = -1
    for col, key, label, year in months:
        if _is_total(_cell(month_row[col] if col < len(month_row) else None)):
            current = None
            previous_col = col
            continue
        if previous_col >= 0 and _crossed_total(month_row, previous_col, col):
            current = None
        text = _cell(product_row[col] if col < len(product_row) else None)
        if _is_product_text(text):
            if current is None or current["product"] != text:
                current = {"product": text, "months": []}
                groups.append(current)
        if current is None:
            previous_col = col
            continue
        current["months"].append((col, key, label, year))
        previous_col = col
    return [group for group in groups if group["months"]]


def _product_row_index(
    matrix: Sequence[Sequence[Any]],
    month_idx: int,
    months: Sequence[MonthCol],
) -> Optional[int]:
    ranked: List[Tuple[int, int, int]] = []
    for idx in (month_idx - 1, month_idx + 1):
        if idx < 0 or idx >= len(matrix) or _month_columns(matrix[idx]):
            continue
        labels = _labels_for_months(matrix[idx], months)
        if not labels:
            continue
        keywords = sum(1 for label in labels if _KEYWORD_PRODUCT.search(label))
        above = 1 if idx < month_idx else 0
        ranked.append((keywords, above, idx))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][2]


def _customer_column(months: Sequence[MonthCol]) -> int:
    month_cols = {col for col, _key, _label, _year in months}
    for col in range(0, min(month_cols) if month_cols else 0):
        if col not in month_cols:
            return col
    return 0


def _skip_customer(text: str) -> bool:
    if not text or _SKIP_ROW.match(text) or _is_total(text):
        return True
    if text.casefold() in _HEADER_WORDS:
        return True
    if _month_spec(text):
        return True
    return False


def detect_cross_product_matrix(matrix: Sequence[Sequence[Any]]) -> bool:
    return bool(_find_layouts(matrix))


def _find_layouts(matrix: Sequence[Sequence[Any]]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for month_idx, row in enumerate(matrix[:80]):
        months = _month_columns(row)
        if len(months) < 2:
            continue
        product_idx = _product_row_index(matrix, month_idx, months)
        if product_idx is None:
            continue
        groups = _build_groups(matrix[product_idx], row, months)
        if not groups:
            continue
        found.append(
            {
                "month_idx": month_idx,
                "product_idx": product_idx,
                "groups": groups,
                "customer_col": _customer_column(months),
                "header_end": max(month_idx, product_idx),
                "month_count": sum(len(group["months"]) for group in groups),
            }
        )
    chosen: List[Dict[str, Any]] = []
    covered: set[int] = set()
    for item in sorted(found, key=lambda layout: (-int(layout["month_count"]), int(layout["month_idx"]))):
        rows = {int(item["month_idx"]), int(item["product_idx"])}
        if rows & covered:
            continue
        covered |= rows
        chosen.append(item)
    chosen.sort(key=lambda layout: int(layout["month_idx"]))
    return chosen


def _period_for(key: str, year: Optional[int], fallback_fy: int) -> Tuple[str, Optional[str]]:
    month_num = month_number_from_key(key)
    if not month_num:
        return "", None
    fy_start = fy_start_for_calendar_month(month_num, year) if year else fallback_fy
    quarter = 1 if month_num in (4, 5, 6) else 2 if month_num in (7, 8, 9) else 3 if month_num in (10, 11, 12) else 4
    period = quarter_label(fy_start, quarter)
    calendar_year = year if year else (fy_start + 1 if month_num <= 3 else fy_start)
    return period, month_label(month_num, calendar_year)


def _quarter_phrase(period: str) -> str:
    spec = parse_quarter_label(period or "")
    if spec and spec.year is not None and spec.kind == "quarter" and spec.quarter:
        return f"Q{spec.quarter} {fy_short(spec.year)}"
    return period


def _confidence(*, customers: bool, products: bool, months: bool, numeric: bool, quarter: bool) -> float:
    return float(
        (25 if customers else 0)
        + (25 if products else 0)
        + (20 if months else 0)
        + (20 if numeric else 0)
        + (10 if quarter else 0)
    )


def extract_cross_product_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    distributor_label: str = "",
) -> Optional[Dict[str, Any]]:
    """Expand each product's month columns into Customer / Product / Qty rows."""
    layouts = _find_layouts(matrix)
    if not layouts:
        return None
    fallback_fy = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )
    rows: List[Dict[str, Any]] = []
    customers: List[str] = []
    products: List[str] = []
    qty_ok = 0
    skipped_invalid = 0
    quarter_ok = False
    groups: List[Dict[str, Any]] = []

    for index, layout in enumerate(layouts):
        customer_col = int(layout["customer_col"])
        groups.extend(layout["groups"])
        start = int(layout["header_end"]) + 1
        end = len(matrix)
        if index + 1 < len(layouts):
            nxt = layouts[index + 1]
            end = min(int(nxt["month_idx"]), int(nxt["product_idx"]))
        for group in layout["groups"]:
            product = str(group["product"])
            if product not in products:
                products.append(product)
            for raw in matrix[start:end]:
                customer = _cell(raw[customer_col] if customer_col < len(raw) else None)
                if _skip_customer(customer):
                    continue
                for col, key, _label, year in group["months"]:
                    value = raw[col] if col < len(raw) else None
                    if value is None or (
                        not isinstance(value, (int, float, Decimal)) and _cell(value) == ""
                    ):
                        continue
                    try:
                        qty, qty_display = parse_quantity(value)
                    except (ValueError, ArithmeticError):
                        skipped_invalid += 1
                        continue
                    if qty == 0:
                        continue
                    if qty < 0:
                        skipped_invalid += 1
                        continue
                    period, source_month = _period_for(key, year, fallback_fy)
                    if not period:
                        continue
                    quarter_ok = True
                    payload: Dict[str, Any] = {
                        "customer_name": customer,
                        "product": product,
                        "sales_quantity": Decimal(str(qty)),
                        "sales_quantity_display": qty_display,
                        "period": period,
                        "reporting_quarter": period,
                    }
                    if source_month:
                        payload["source_month"] = source_month
                    rows.append(payload)
                    qty_ok += 1

    if not rows:
        return None
    for row in rows:
        name = str(row.get("customer_name") or "")
        if name and name not in customers:
            customers.append(name)

    periods = [str(row.get("period") or "") for row in rows if row.get("period")]
    quarter = _quarter_phrase(max(set(periods), key=periods.count)) if periods else ""
    confidence = _confidence(
        customers=bool(customers),
        products=bool(products),
        months=any(group["months"] for group in groups),
        numeric=qty_ok > 0,
        quarter=quarter_ok,
    )
    return {
        "rows": rows,
        "products": products,
        "products_detected": len(products),
        "customers_detected": len(customers),
        "quarter": quarter,
        "distributor": (distributor_label or "").strip(),
        "skipped_invalid": skipped_invalid,
        "skipped_blank": 0,
        "skipped_total": 0,
        "quantity_ok": qty_ok,
        "quantity_fail": skipped_invalid,
        "errors": [],
        "fiscal_year_start": fallback_fy,
        "header_row": int(layouts[0]["month_idx"]) + 1,
        "monthly_pivot": True,
        "layout": "cross_product_matrix",
        "score": confidence,
        "confidence": confidence,
        "detected": True,
        "llm_used": False,
    }
