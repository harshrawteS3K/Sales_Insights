"""Sales Analysis metadata layout (Kemco).

Product is not a column. It is the text after ``Item Group :``.
Customers are ``Account Name`` and quantities are ``Nett Sale Qty.``.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from app.core.logging import get_logger
from app.erp_parser.fiscal_quarters import (
    quarter_label,
    resolve_fy_start_year,
)
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.utils.period_calendar import quarter_of_month
from app.utils.quantity import format_quantity, normalize_unit, parse_quantity

logger = get_logger(__name__)

_TOTAL_RE = re.compile(r"^(grand\s+|sub\s+)?totals?\b", re.IGNORECASE)
_ITEM_GROUP_RE = re.compile(r"item\s*group\s*[:：]\s*(.*)$", re.IGNORECASE)
_ITEM_GROUP_LABEL_RE = re.compile(r"^item\s*group\s*[:：]?$", re.IGNORECASE)
_RANGE_RE = re.compile(
    r"from\s+(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\s+to\s+"
    r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})",
    re.IGNORECASE,
)
_QTY_HEADERS = {
    "nett sale qty",
    "nett sale qty.",
    "net sale qty",
    "net sale qty.",
    "sales qty",
    "sales qty.",
}
_CUSTOMER_HEADERS = {"account name", "account"}
_UNIT_HEADERS = {"unit", "uom"}


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("_x000D_", " ").strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _norm(value: Any) -> str:
    text = _cell(value).lower().rstrip(":").strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s./]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_blank_row(row: Sequence[Any]) -> bool:
    return not any(_cell(c) for c in row)


def _is_total_label(text: str) -> bool:
    return bool(_TOTAL_RE.match((text or "").strip()))


def _row_text(row: Sequence[Any]) -> str:
    parts = [_cell(c) for c in row if _cell(c)]
    unique: List[str] = []
    for part in parts:
        if part not in unique:
            unique.append(part)
    return " ".join(unique)


def _product_on_row(row: Sequence[Any]) -> str:
    for idx, raw in enumerate(row):
        text = _cell(raw)
        if not text:
            continue
        match = _ITEM_GROUP_RE.search(text)
        if match:
            product = match.group(1).strip(" :-")
            if product:
                return re.sub(r"\s+", " ", product).strip()
            for nxt in row[idx + 1 :]:
                follower = _cell(nxt)
                if follower:
                    return follower
        if _ITEM_GROUP_LABEL_RE.match(text):
            for nxt in row[idx + 1 :]:
                follower = _cell(nxt)
                if follower:
                    return follower
    return ""


def _header_columns(row: Sequence[Any]) -> Optional[Tuple[int, int, Optional[int]]]:
    customer = qty = unit = None
    for idx, raw in enumerate(row):
        key = _norm(raw).rstrip(".").strip()
        dotted = _norm(raw)
        if customer is None and (key in _CUSTOMER_HEADERS or dotted in _CUSTOMER_HEADERS):
            customer = idx
        if qty is None and (key in _QTY_HEADERS or dotted in _QTY_HEADERS):
            qty = idx
        if unit is None and key in _UNIT_HEADERS:
            unit = idx
    if customer is None or qty is None:
        return None
    return customer, qty, unit


def _sheet_has_phrase(matrix: Sequence[Sequence[Any]], phrase: str) -> bool:
    needle = phrase.lower()
    for row in matrix[:80]:
        for raw in row:
            if needle in _norm(raw) or needle in _cell(raw).lower():
                return True
    return False


def detect_metadata_layout(sheet: Sequence[Sequence[Any]]) -> bool:
    """True for Sales Analysis sheets whose product is an Item Group line."""
    if not sheet:
        return False
    if not _sheet_has_phrase(sheet, "sales analysis"):
        return False
    if not any(_product_on_row(row) or _ITEM_GROUP_RE.search(_row_text(row)) for row in sheet[:80]):
        return False
    if not _sheet_has_phrase(sheet, "account name"):
        return False
    if not (_sheet_has_phrase(sheet, "nett sale qty") or _sheet_has_phrase(sheet, "net sale qty")):
        return False
    return any(_header_columns(row) for row in sheet[:80])


def _distributor_name(matrix: Sequence[Sequence[Any]]) -> str:
    for row in matrix[:8]:
        texts = [_cell(c) for c in row if _cell(c)]
        if not texts:
            continue
        label = texts[0]
        folded = label.lower()
        if "sales analysis" in folded or folded.startswith("item group"):
            continue
        if folded.startswith("from ") or _header_columns(row):
            continue
        return label
    return ""


def _dmy(day: int, month: int, year: int) -> Optional[date]:
    if day > 12 and month <= 12:
        pass
    elif month > 12 and day <= 12:
        day, month = month, day
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _period_from_sheet(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int],
    reporting_quarter: Optional[str],
) -> Optional[str]:
    for row in matrix[:40]:
        text = _row_text(row)
        match = _RANGE_RE.search(text)
        if not match:
            continue
        start = _dmy(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        end = _dmy(int(match.group(4)), int(match.group(5)), int(match.group(6)))
        if not start or not end:
            continue
        start_q = quarter_of_month(start.month)
        end_q = quarter_of_month(end.month)
        fy = start.year if start.month >= 4 else start.year - 1
        if start_q == end_q and (end.year if end.month >= 4 else end.year - 1) == fy:
            return quarter_label(fy, start_q)
        break
    explicit = (reporting_quarter or "").strip()
    if explicit:
        return explicit
    if fiscal_year_start:
        return None
    return None


def _unit_label(raw: Any) -> str:
    text = _cell(raw).strip().rstrip(".").upper()
    if not text:
        return ""
    normalized = normalize_unit(text)
    if normalized in {"KG", "MT"}:
        return normalized
    return text


def extract_metadata_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Expand Account Name / Nett Sale Qty rows using the Item Group product."""
    if not detect_metadata_layout(matrix):
        return None

    distributor = _distributor_name(matrix)
    period = _period_from_sheet(
        matrix,
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )
    fy_start = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=period or reporting_quarter,
    )
    current_product = ""
    for row in matrix[:80]:
        found = _product_on_row(row)
        if found:
            current_product = found
            break
    if not current_product:
        return None

    customer_col: Optional[int] = None
    qty_col: Optional[int] = None
    unit_col: Optional[int] = None
    header_row = 1
    rows: List[Dict[str, Any]] = []
    skipped_total = 0
    skipped_blank = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0
    products: List[str] = []

    for idx, row in enumerate(matrix):
        found = _product_on_row(row)
        if found:
            current_product = found
            if found not in products:
                products.append(found)
            continue
        header = _header_columns(row)
        if header:
            customer_col, qty_col, unit_col = header
            header_row = idx + 1
            continue
        if customer_col is None or qty_col is None or _is_blank_row(row):
            skipped_blank += 1
            continue
        customer = _cell(row[customer_col]) if customer_col < len(row) else ""
        if not customer:
            skipped_blank += 1
            continue
        if _is_total_label(customer) or _norm(customer).rstrip(".").strip() in _CUSTOMER_HEADERS:
            skipped_total += 1
            continue
        raw_qty = row[qty_col] if qty_col < len(row) else None
        if raw_qty is None or _cell(raw_qty) == "" and not isinstance(raw_qty, (int, float, Decimal)):
            skipped_blank += 1
            continue
        try:
            qty, _disp = parse_quantity(raw_qty)
        except (ValueError, ArithmeticError):
            qty_fail += 1
            continue
        if qty == 0:
            continue
        if qty < 0:
            skipped_invalid += 1
            continue
        amount = Decimal(str(qty))
        payload: Dict[str, Any] = {
            "customer_name": customer,
            "product": current_product,
            "sales_quantity": amount,
            "sales_quantity_display": format_quantity(amount),
        }
        if period:
            payload["period"] = period
            payload["reporting_quarter"] = period
        if unit_col is not None and unit_col < len(row):
            unit = _unit_label(row[unit_col])
            if unit:
                payload["original_unit"] = unit
        rows.append(payload)
        qty_ok += 1

    if current_product and current_product not in products:
        products.append(current_product)

    return {
        "rows": rows,
        "products_detected": len(products),
        "products": products,
        "distributor": distributor,
        "product": products[0] if len(products) == 1 else ", ".join(products),
        "skipped_total": skipped_total,
        "skipped_blank": skipped_blank,
        "skipped_invalid": skipped_invalid,
        "quantity_ok": qty_ok,
        "quantity_fail": qty_fail,
        "errors": [],
        "fiscal_year_start": fy_start,
        "header_row": header_row,
        "monthly_pivot": False,
        "layout": "metadata_sales",
        "score": round(min(98.0, 80.0 + len(rows) * 0.4), 2),
        "detected": True,
    }


def extract_metadata_workbook(
    path: Union[str, Path],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    sheet_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return the Sales Analysis sheet with the most extracted rows."""
    file_path = Path(path)
    try:
        sheets = [sheet_name] if sheet_name else list_candidate_sheets(file_path)
    except Exception:  # noqa: BLE001
        return None

    best: Optional[Dict[str, Any]] = None
    best_sheet = ""
    detected = False
    for name in sheets:
        if not name:
            continue
        try:
            matrix = read_sheet_matrix(file_path, name)
        except Exception:  # noqa: BLE001
            continue
        if not detect_metadata_layout(matrix):
            continue
        detected = True
        extracted = extract_metadata_rows(
            matrix,
            fiscal_year_start=fiscal_year_start,
            reporting_quarter=reporting_quarter,
        )
        if not extracted:
            continue
        extracted["sheet_name"] = name
        if best is None or len(extracted.get("rows") or []) > len(best.get("rows") or []):
            best = extracted
            best_sheet = name
    if best is None:
        if not detected:
            return None
        return {
            "rows": [],
            "detected": True,
            "layout": "metadata_sales",
            "distributor": "",
            "product": "",
            "quantity_ok": 0,
            "quantity_fail": 0,
            "skipped_invalid": 0,
            "score": 0,
            "header_row": 1,
        }
    best["sheet_name"] = best_sheet
    logger.info(
        "ERP Strategy: Metadata Parser\nDistributor: {}\nProduct: {}\nRows: {}",
        best.get("distributor") or "",
        best.get("product") or "",
        len(best.get("rows") or []),
    )
    return best
