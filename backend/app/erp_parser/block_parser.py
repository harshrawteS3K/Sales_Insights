"""Repeating product-block ERP layout (BPS).

A product title sits on its own row. The next row is ``Party`` plus month
columns (text such as Apr/May/Jun, or Excel datetime months). Customer rows
follow until TOTAL or the next product title. There is no Product column.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from app.core.logging import get_logger
from app.erp_parser.fiscal_quarters import (
    month_key_to_quarter,
    month_number_from_key,
    quarter_label,
    resolve_fy_start_year,
    source_month_label,
)
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.utils.quantity import format_quantity, parse_quantity

logger = get_logger(__name__)

_PARTY_HEADERS = {"party", "party name"}
_TOTAL_RE = re.compile(r"^(grand\s+|sub\s+)?totals?\b", re.IGNORECASE)
_MONTH_TOKEN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
)
_MONTH_ONLY_RE = re.compile(rf"^(?:{_MONTH_TOKEN})$", re.IGNORECASE)
_MONTH_YEAR_RE = re.compile(
    rf"^(?:{_MONTH_TOKEN})[\s\-/_.']*\d{{2,4}}$",
    re.IGNORECASE,
)
_DAY_MONTH_YEAR_RE = re.compile(
    rf"^\d{{1,2}}[\s\-/_.']+(?:{_MONTH_TOKEN})[\s\-/_.']*\d{{2,4}}$",
    re.IGNORECASE,
)
_MONTH_KEY = {
    "jan": "january",
    "january": "january",
    "feb": "february",
    "february": "february",
    "mar": "march",
    "march": "march",
    "apr": "april",
    "april": "april",
    "may": "may",
    "jun": "june",
    "june": "june",
    "jul": "july",
    "july": "july",
    "aug": "august",
    "august": "august",
    "sep": "september",
    "sept": "september",
    "september": "september",
    "oct": "october",
    "october": "october",
    "nov": "november",
    "november": "november",
    "dec": "december",
    "december": "december",
}
_MONTH_BY_NUMBER = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}
_SKIP_HEADER = {"total", "grand total", "sub total", "subtotal", "qty", "quantity", "mt", "kg", "unit", "uom"}


def _cell(value: Any) -> str:
    if value is None or isinstance(value, (datetime, date)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _norm(value: Any) -> str:
    text = _cell(value).lower().rstrip(":").strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s./]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_blank_row(row: Sequence[Any]) -> bool:
    for raw in row:
        if isinstance(raw, (datetime, date)):
            return False
        if _cell(raw):
            return False
    return True


def _is_pure_number(raw: Any) -> bool:
    if isinstance(raw, bool) or isinstance(raw, (datetime, date)):
        return False
    if isinstance(raw, (int, float, Decimal)):
        return True
    text = _cell(raw).replace(",", "")
    return bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text))


def _is_total_label(text: str) -> bool:
    return bool(_TOTAL_RE.match((text or "").strip()))


def _party_column(row: Sequence[Any]) -> int:
    for idx, raw in enumerate(row):
        if _norm(raw) in _PARTY_HEADERS:
            return idx
    return -1


def _is_party_header(row: Sequence[Any]) -> bool:
    return _party_column(row) >= 0


def _year_from_token(token: str) -> Optional[int]:
    digits = re.sub(r"\D", "", token or "")
    if len(digits) == 4:
        year = int(digits)
    elif len(digits) == 2:
        year = 2000 + int(digits)
    else:
        return None
    if 1990 <= year <= 2100:
        return year
    return None


def _from_calendar_date(d: date) -> Tuple[str, str, int]:
    key = _MONTH_BY_NUMBER[d.month]
    return key, f"{d.strftime('%B')} {d.year}", d.year


def _month_spec(raw: Any) -> Optional[Tuple[str, str, Optional[int]]]:
    """Return ``(month_key, header_label, calendar_year)`` for a month header."""
    if isinstance(raw, datetime):
        key, label, year = _from_calendar_date(raw.date())
        return key, label, year
    if isinstance(raw, date):
        key, label, year = _from_calendar_date(raw)
        return key, label, year

    text = _cell(raw)
    if not text:
        return None

    iso = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if iso:
        year, month = int(iso.group(1)), int(iso.group(2))
        if 1990 <= year <= 2100 and 1 <= month <= 12:
            key = _MONTH_BY_NUMBER[month]
            return key, f"{date(year, month, 1).strftime('%B')} {year}", year

    dmy = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text)
    if dmy:
        day, month, year = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        if day > 12 and month <= 12:
            pass
        elif month > 12 and day <= 12:
            day, month = month, day
        if 1990 <= year <= 2100 and 1 <= month <= 12:
            key = _MONTH_BY_NUMBER[month]
            return key, f"{date(year, month, 1).strftime('%B')} {year}", year

    cleaned = text.replace(".", " ")
    if _MONTH_ONLY_RE.match(cleaned.strip()):
        token = re.match(rf"^({_MONTH_TOKEN})", cleaned.strip(), re.IGNORECASE)
        key = _MONTH_KEY[token.group(1).lower()] if token else ""
        return (key, text, None) if key else None

    if _MONTH_YEAR_RE.match(cleaned.strip()) or _DAY_MONTH_YEAR_RE.match(cleaned.strip()):
        token = re.search(rf"({_MONTH_TOKEN})", cleaned, re.IGNORECASE)
        year_token = re.search(r"(\d{2,4})\s*$", cleaned.strip())
        if token:
            key = _MONTH_KEY[token.group(1).lower()]
            year = _year_from_token(year_token.group(1) if year_token else "")
            label = text
            if year and key:
                month_num = month_number_from_key(key)
                if month_num:
                    label = f"{date(year, month_num, 1).strftime('%B')} {year}"
            return key, label, year
    return None


def _month_columns(row: Sequence[Any]) -> List[Tuple[int, str, str, Optional[int]]]:
    party_col = _party_column(row)
    if party_col < 0:
        return []
    found: List[Tuple[int, str, str, Optional[int]]] = []
    for idx, raw in enumerate(row):
        if idx == party_col:
            continue
        spec = _month_spec(raw)
        if spec:
            key, label, year = spec
            found.append((idx, label, key, year))
            continue
        text = _norm(raw)
        if not text or text in _SKIP_HEADER or _is_total_label(text):
            continue
        return []
    if len(found) < 2:
        return []
    return found


def _single_product_title(row: Sequence[Any]) -> str:
    """A product title row is one text cell (merged copies count as one)."""
    unique: List[str] = []
    for raw in row:
        if isinstance(raw, (datetime, date)) or _month_spec(raw):
            return ""
        text = _cell(raw)
        if not text or _is_total_label(text):
            continue
        if _norm(text) in _PARTY_HEADERS or _norm(text) in _SKIP_HEADER:
            return ""
        if _is_pure_number(raw):
            continue
        if text not in unique:
            unique.append(text)
    if len(unique) != 1:
        return ""
    return unique[0]


def _party_row_after(matrix: Sequence[Sequence[Any]], title_idx: int) -> int:
    nxt = title_idx + 1
    if nxt >= len(matrix):
        return -1
    if _is_blank_row(matrix[nxt]):
        nxt += 1
    if nxt >= len(matrix):
        return -1
    if _is_party_header(matrix[nxt]) and _month_columns(matrix[nxt]):
        return nxt
    return -1


def detect_block_product_layout(sheet: Sequence[Sequence[Any]]) -> bool:
    """True when a product title is followed by Party and month columns."""
    if not sheet:
        return False
    for idx, row in enumerate(sheet):
        if not _single_product_title(row):
            continue
        if _party_row_after(sheet, idx) >= 0:
            return True
    return False


def extract_product_block_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Expand Party/month blocks into Customer / Product / Qty rows."""
    if not detect_block_product_layout(matrix):
        return None

    fallback_fy = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )
    current_product = ""
    party_col = 0
    month_cols: List[Tuple[int, str, str, Optional[int]]] = []
    rows: List[Dict[str, Any]] = []
    products_detected = 0
    skipped_total = 0
    skipped_blank = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0

    idx = 0
    while idx < len(matrix):
        party_at = _party_row_after(matrix, idx)
        title = _single_product_title(matrix[idx]) if party_at >= 0 else ""
        if title and party_at >= 0:
            current_product = title
            month_cols = _month_columns(matrix[party_at])
            party_col = _party_column(matrix[party_at])
            products_detected += 1
            idx = party_at + 1
            continue

        row = matrix[idx]
        idx += 1
        if _is_blank_row(row):
            skipped_blank += 1
            continue
        label = _cell(row[party_col]) if 0 <= party_col < len(row) else ""
        if not label:
            label_hit = next((_cell(c) for c in row if _cell(c)), "")
            label = label_hit
        if not label:
            skipped_blank += 1
            continue
        if _is_total_label(label):
            skipped_total += 1
            continue
        if not current_product or not month_cols:
            continue
        if _norm(label) in _PARTY_HEADERS or _month_spec(label):
            continue

        customer = label.strip()
        emitted = 0
        for col, header, key, year in month_cols:
            raw = row[col] if col < len(row) else None
            if raw is None or (not isinstance(raw, (int, float, Decimal)) and _cell(raw) == ""):
                continue
            try:
                qty, _disp = parse_quantity(raw)
            except (ValueError, ArithmeticError):
                qty_fail += 1
                continue
            if qty == 0:
                continue
            if qty < 0:
                skipped_invalid += 1
                continue
            q_num = month_key_to_quarter(key)
            month_num = month_number_from_key(key)
            if not q_num or not month_num:
                continue
            fy_start = fallback_fy
            if year:
                fy_start = year if month_num >= 4 else year - 1
            period = quarter_label(fy_start, q_num)
            amount = Decimal(str(qty))
            payload: Dict[str, Any] = {
                "customer_name": customer,
                "product": current_product,
                "sales_quantity": amount,
                "sales_quantity_display": format_quantity(amount),
                "period": period,
                "reporting_quarter": period,
            }
            src = source_month_label(key, fy_start, header)
            if src:
                payload["source_month"] = src
            rows.append(payload)
            qty_ok += 1
            emitted += 1
        if emitted == 0:
            skipped_blank += 1

    return {
        "rows": rows,
        "products_detected": products_detected,
        "skipped_total": skipped_total,
        "skipped_blank": skipped_blank,
        "skipped_invalid": skipped_invalid,
        "quantity_ok": qty_ok,
        "quantity_fail": qty_fail,
        "errors": [],
        "fiscal_year_start": fallback_fy,
        "monthly_pivot": True,
        "layout": "product_blocks",
        "score": round(min(98.0, 72.0 + len(rows) * 0.4), 2),
    }


def extract_product_blocks_workbook(
    path: Union[str, Path],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    sheet_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Scan sheets. Return the block layout, or a marker when detection hits with no rows."""
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
        if not detect_block_product_layout(matrix):
            continue
        detected = True
        extracted = extract_product_block_rows(
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
            "products_detected": 0,
            "sheet_name": "",
            "layout": "product_blocks",
            "detected": True,
            "quantity_ok": 0,
            "quantity_fail": 0,
            "skipped_invalid": 0,
            "skipped_total": 0,
            "skipped_blank": 0,
            "errors": [],
            "score": 0,
        }
    best["sheet_name"] = best_sheet
    best["detected"] = True
    logger.info(
        "ERP Block Parser activated\nfile={}\nproducts_detected={}\nrows_extracted={}",
        file_path.name,
        int(best.get("products_detected") or 0),
        len(best.get("rows") or []),
    )
    return best
