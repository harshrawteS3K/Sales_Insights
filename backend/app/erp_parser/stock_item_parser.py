"""Tally Stock Item Register layout (SK Trading).

Product is the text immediately above ``Stock Item Register``.
Customer is ``Particulars``. Quantity is the Quantity column under Outwards.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from app.core.logging import get_logger
from app.erp_parser.fiscal_quarters import quarter_label, resolve_fy_start_year
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.utils.period_calendar import (
    fy_short,
    fy_start_for_calendar_month,
    month_label,
    parse_quarter_label,
    quarter_of_month,
)
from app.utils.quantity import format_quantity, parse_quantity

logger = get_logger(__name__)

_REGISTER_RE = re.compile(r"stock\s*item\s*register", re.IGNORECASE)
_SKIP_ROW_RE = re.compile(
    r"^(grand\s+|sub\s+)?totals?\b$"
    r"|^(opening|closing)(\s+balance|\s+stock)?$"
    r"|^(voucher\s*no\.?|vch\s*type|vch\s*no\.?)$",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_SUBHEADER = {"quantity", "qty", "rate", "value", "amount", "balance", "inwards", "outwards"}


def _cell(value: Any) -> str:
    if value is None or isinstance(value, (datetime, date)):
        return ""
    text = str(value).replace("\n", " ").replace("_x000D_", " ").strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _norm(value: Any) -> str:
    text = _cell(value).lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s./]", " ", text)
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def _is_blank(row: Sequence[Any]) -> bool:
    for raw in row:
        if isinstance(raw, (datetime, date)) or _cell(raw):
            return False
    return True


def _is_register_row(row: Sequence[Any]) -> bool:
    return any(_REGISTER_RE.search(_cell(raw)) for raw in row)


def _is_qty_header(raw: Any) -> bool:
    text = _norm(raw)
    return text in {"quantity", "qty", "nett sale qty", "net sale qty", "sales qty"} or (
        "outward" in text and ("qty" in text or "quantity" in text)
    )


def _is_subheader(row: Sequence[Any]) -> bool:
    labels = [_norm(c) for c in row if _norm(c)]
    if not labels:
        return False
    if any(label in {"particulars", "particular", "date"} for label in labels):
        return False
    return all(any(token in label for token in _SUBHEADER) or "outward" in label or "inward" in label for label in labels)


def _product_above(matrix: Sequence[Sequence[Any]], register_idx: int) -> str:
    for lookback in (1, 2):
        prev = register_idx - lookback
        if prev < 0:
            return ""
        if _is_blank(matrix[prev]):
            continue
        if _is_register_row(matrix[prev]):
            return ""
        texts: List[str] = []
        for raw in matrix[prev]:
            if isinstance(raw, (datetime, date)):
                return ""
            text = _cell(raw)
            if not text:
                continue
            if _REGISTER_RE.search(text) or _SKIP_ROW_RE.match(text):
                return ""
            if text not in texts:
                texts.append(text)
        if len(texts) == 1:
            return texts[0]
        return ""
    return ""


def _particulars_col(row: Sequence[Any]) -> int:
    for idx, raw in enumerate(row):
        if _norm(raw) in {"particulars", "particular"}:
            return idx
    return -1


def _outwards_quantity_col(
    matrix: Sequence[Sequence[Any]],
    header_idx: int,
) -> Tuple[int, int]:
    """Return ``(quantity_col, last_header_row_index)``."""
    header = matrix[header_idx]
    sub_idx = header_idx + 1 if header_idx + 1 < len(matrix) and _is_subheader(matrix[header_idx + 1]) else None
    qty_row = matrix[sub_idx] if sub_idx is not None else header
    parent = header if sub_idx is not None else None
    qty_cols = [idx for idx, raw in enumerate(qty_row) if _is_qty_header(raw)]
    outwards_on_qty = [
        idx
        for idx, raw in enumerate(qty_row)
        if "outward" in _norm(raw) and ("qty" in _norm(raw) or "quantity" in _norm(raw))
    ]
    if outwards_on_qty:
        return outwards_on_qty[0], sub_idx if sub_idx is not None else header_idx
    if parent is not None:
        outward_idx = [idx for idx, raw in enumerate(parent) if "outward" in _norm(raw)]
        if outward_idx and qty_cols:
            lo, hi = min(outward_idx), max(outward_idx)
            under = [idx for idx in qty_cols if lo <= idx <= hi]
            if under:
                return under[0], sub_idx if sub_idx is not None else header_idx
    outward_same = [idx for idx, raw in enumerate(header) if "outward" in _norm(raw)]
    if outward_same and qty_cols:
        after = [idx for idx in qty_cols if idx > outward_same[0]]
        if after:
            return after[0], sub_idx if sub_idx is not None else header_idx
        if any(_is_qty_header(header[idx]) for idx in outward_same):
            return outward_same[0], header_idx
    if len(qty_cols) == 1 and any("outward" in _norm(raw) for raw in list(header) + list(qty_row)):
        return qty_cols[0], sub_idx if sub_idx is not None else header_idx
    return -1, header_idx


def _as_date(raw: Any) -> Optional[date]:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = _cell(raw)
    if not text:
        return None
    named = re.match(
        r"^(\d{1,2})[-/\s.]([A-Za-z]{3,9})[-/\s.](\d{2,4})$",
        text,
    )
    if named:
        month = _MONTHS.get(named.group(2).lower())
        year = int(named.group(3))
        if year < 100:
            year += 2000
        if month:
            try:
                return date(year, month, int(named.group(1)))
            except ValueError:
                return None
    numeric = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", text)
    if numeric:
        day, month, year = int(numeric.group(1)), int(numeric.group(2)), int(numeric.group(3))
        if month > 12 and day <= 12:
            day, month = month, day
        try:
            return date(year, month, day)
        except ValueError:
            return None
    iso = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    return None


def _period_for_date(value: date) -> str:
    fy = fy_start_for_calendar_month(value.month, value.year)
    return quarter_label(fy, quarter_of_month(value.month))


def _quarter_phrase(period: str) -> str:
    spec = parse_quarter_label(period or "")
    if spec and spec.year is not None and spec.kind == "quarter" and spec.quarter:
        return f"Q{spec.quarter} {fy_short(spec.year)}"
    if spec and spec.year is not None and spec.kind == "year":
        return fy_short(spec.year)
    return period


def _sheet_range_period(matrix: Sequence[Sequence[Any]]) -> Optional[str]:
    for row in matrix[:25]:
        dates = [_as_date(raw) for raw in row]
        found = [item for item in dates if item]
        text = " ".join(_cell(raw) for raw in row if _cell(raw))
        named = re.findall(
            r"(\d{1,2}[-/\s.][A-Za-z]{3,9}[-/\s.]\d{2,4}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})",
            text,
        )
        for token in named:
            parsed = _as_date(token)
            if parsed:
                found.append(parsed)
        if len(found) >= 2:
            start, end = found[0], found[1]
            if _period_for_date(start) == _period_for_date(end):
                return _period_for_date(start)
        elif len(found) == 1 and re.search(r"\bto\b", text, re.IGNORECASE):
            return _period_for_date(found[0])
    return None


def detect_stock_item_register(sheet: Sequence[Sequence[Any]]) -> bool:
    """True when a product title sits above Stock Item Register and Outwards Quantity."""
    if not sheet:
        return False
    for idx, row in enumerate(sheet):
        if not _is_register_row(row):
            continue
        if not _product_above(sheet, idx):
            continue
        for look in range(idx + 1, min(idx + 12, len(sheet))):
            if _particulars_col(sheet[look]) < 0:
                continue
            qty_col, _last = _outwards_quantity_col(sheet, look)
            if qty_col >= 0:
                return True
    return False


def extract_stock_item_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    distributor_label: str = "",
) -> Optional[Dict[str, Any]]:
    if not detect_stock_item_register(matrix):
        return None

    fallback_period = (reporting_quarter or "").strip() or _sheet_range_period(matrix) or ""
    fallback_fy = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=fallback_period or reporting_quarter,
    )
    registers: List[Tuple[int, str]] = []
    for idx, row in enumerate(matrix):
        if _is_register_row(row):
            product = _product_above(matrix, idx)
            if product:
                registers.append((idx, product))
    if not registers:
        return None

    rows: List[Dict[str, Any]] = []
    products: List[str] = []
    skipped_total = 0
    skipped_blank = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0
    header_row = 1

    for reg_pos, (reg_idx, product) in enumerate(registers):
        if product not in products:
            products.append(product)
        end = registers[reg_pos + 1][0] if reg_pos + 1 < len(registers) else len(matrix)
        particulars = -1
        qty_col = -1
        data_from = reg_idx + 1
        date_col = -1
        for look in range(reg_idx + 1, min(reg_idx + 12, end)):
            col = _particulars_col(matrix[look])
            if col < 0:
                continue
            found_qty, last_header = _outwards_quantity_col(matrix, look)
            if found_qty < 0:
                continue
            particulars = col
            qty_col = found_qty
            data_from = last_header + 1
            header_row = look + 1
            for idx, raw in enumerate(matrix[look]):
                if _norm(raw) == "date":
                    date_col = idx
                    break
            break
        if particulars < 0 or qty_col < 0:
            continue
        for row in matrix[data_from:end]:
            if _is_blank(row) or _is_register_row(row):
                skipped_blank += 1
                continue
            customer = _cell(row[particulars]) if particulars < len(row) else ""
            if not customer:
                skipped_blank += 1
                continue
            if _SKIP_ROW_RE.match(customer) or _norm(customer) in {"particulars", "particular"}:
                skipped_total += 1
                continue
            raw_qty = row[qty_col] if qty_col < len(row) else None
            if raw_qty is None or (_cell(raw_qty) == "" and not isinstance(raw_qty, (int, float, Decimal))):
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
            tx_date = None
            if date_col >= 0 and date_col < len(row):
                tx_date = _as_date(row[date_col])
            if tx_date is None:
                tx_date = next((_as_date(raw) for raw in row if _as_date(raw)), None)
            period = _period_for_date(tx_date) if tx_date else fallback_period
            amount = Decimal(str(qty))
            payload: Dict[str, Any] = {
                "customer_name": customer,
                "product": product,
                "sales_quantity": amount,
                "sales_quantity_display": format_quantity(amount),
            }
            if period:
                payload["period"] = period
                payload["reporting_quarter"] = period
            if tx_date:
                payload["source_month"] = month_label(tx_date.month, tx_date.year)
            rows.append(payload)
            qty_ok += 1

    quarter = ""
    periods = [str(row.get("period") or "") for row in rows if row.get("period")]
    if periods:
        quarter = _quarter_phrase(max(set(periods), key=periods.count))
    elif fallback_period:
        quarter = _quarter_phrase(fallback_period)

    return {
        "rows": rows,
        "products": products,
        "product": products[0] if len(products) == 1 else ", ".join(products),
        "distributor": (distributor_label or "").strip(),
        "quarter": quarter,
        "skipped_total": skipped_total,
        "skipped_blank": skipped_blank,
        "skipped_invalid": skipped_invalid,
        "quantity_ok": qty_ok,
        "quantity_fail": qty_fail,
        "errors": [],
        "fiscal_year_start": fallback_fy,
        "header_row": header_row,
        "monthly_pivot": False,
        "layout": "stock_item_register",
        "score": round(min(98.0, 78.0 + len(rows) * 0.3), 2),
        "detected": True,
    }


def extract_stock_item_workbook(
    path: Union[str, Path],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    sheet_name: Optional[str] = None,
    distributor_label: str = "",
) -> Optional[Dict[str, Any]]:
    file_path = Path(path)
    try:
        sheets = [sheet_name] if sheet_name else list_candidate_sheets(file_path)
    except Exception:  # noqa: BLE001
        return None

    best: Optional[Dict[str, Any]] = None
    detected = False
    for name in sheets:
        if not name:
            continue
        try:
            matrix = read_sheet_matrix(file_path, name)
        except Exception:  # noqa: BLE001
            continue
        if not detect_stock_item_register(matrix):
            continue
        detected = True
        extracted = extract_stock_item_rows(
            matrix,
            fiscal_year_start=fiscal_year_start,
            reporting_quarter=reporting_quarter,
            distributor_label=distributor_label,
        )
        if not extracted:
            continue
        extracted["sheet_name"] = name
        if best is None or len(extracted.get("rows") or []) > len(best.get("rows") or []):
            best = extracted
    if best is None:
        if not detected:
            return None
        return {
            "rows": [],
            "detected": True,
            "layout": "stock_item_register",
            "distributor": distributor_label,
            "product": "",
            "quarter": "",
            "quantity_ok": 0,
            "quantity_fail": 0,
            "skipped_invalid": 0,
            "score": 0,
            "header_row": 1,
        }
    logger.info(
        "ERP Strategy : Stock Item Register Parser\n"
        "Distributor : {}\n"
        "Product : {}\n"
        "Quarter : {}\n"
        "Rows Parsed : {}",
        best.get("distributor") or "",
        best.get("product") or "",
        best.get("quarter") or "",
        len(best.get("rows") or []),
    )
    return best
