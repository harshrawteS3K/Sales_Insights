"""Customer × Product × month-column ERP layout.

One header row is ``Customer | Product | Apr-2026 | May-2026 | …``.
Month headers may be Excel datetimes. Each non-empty month cell becomes its
own row. Consolidated storage keeps Financial Year + Quarter only.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from app.core.logging import get_logger
from app.erp_parser.fiscal_quarters import (
    month_number_from_key,
    quarter_label,
    resolve_fy_start_year,
)
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.utils.period_calendar import (
    format_period_display,
    fy_start_for_calendar_month,
    month_label,
    quarter_of_month,
)
from app.utils.quantity import format_quantity, parse_quantity

logger = get_logger(__name__)

_CUSTOMER = {"customer", "customer name", "party", "party name", "particulars", "particular", "buyer"}
_PRODUCT = {"product", "product name", "item", "item name", "material", "material name"}
_IGNORE = {"total", "grand total", "sub total", "subtotal", "unit", "uom", "qty", "quantity"}
_SKIP_ROW = re.compile(r"^(grand\s+|sub\s+)?totals?\b", re.IGNORECASE)
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
_SHORT = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


def _cell(value: Any) -> str:
    if value is None or isinstance(value, (datetime, date)):
        return ""
    text = str(value).replace("\n", " ").strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _norm(value: Any) -> str:
    text = _cell(value).lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s./]", " ", text)
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def _month_spec(raw: Any) -> Optional[Tuple[str, str, Optional[int]]]:
    """Return ``(month_key, header_label, calendar_year)`` for a month header."""
    if isinstance(raw, datetime):
        raw = raw.date()
    if isinstance(raw, date):
        key = _MONTH_BY_NUMBER[raw.month]
        return key, f"{raw.strftime('%B')} {raw.year}", raw.year

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
        if month > 12 and day <= 12:
            day, month = month, day
        if 1990 <= year <= 2100 and 1 <= month <= 12:
            key = _MONTH_BY_NUMBER[month]
            return key, f"{date(year, month, 1).strftime('%B')} {year}", year
    cleaned = text.replace(".", " ").strip()
    if _MONTH_ONLY_RE.match(cleaned):
        token = re.match(rf"^({_MONTH_TOKEN})", cleaned, re.IGNORECASE)
        key = _MONTH_KEY[token.group(1).lower()] if token else ""
        return (key, text, None) if key else None
    if _MONTH_YEAR_RE.match(cleaned) or _DAY_MONTH_YEAR_RE.match(cleaned):
        token = re.search(rf"({_MONTH_TOKEN})", cleaned, re.IGNORECASE)
        year_token = re.search(r"(\d{2,4})\s*$", cleaned)
        if token:
            key = _MONTH_KEY[token.group(1).lower()]
            year = None
            digits = re.sub(r"\D", "", year_token.group(1) if year_token else "")
            if len(digits) == 4:
                year = int(digits)
            elif len(digits) == 2:
                year = 2000 + int(digits)
            label = text
            month_num = month_number_from_key(key)
            if year and month_num and 1990 <= year <= 2100:
                label = f"{date(year, month_num, 1).strftime('%B')} {year}"
            return key, label, year
    return None


def _header_layout(row: Sequence[Any]) -> Optional[Dict[str, Any]]:
    if len(row) < 4:
        return None
    if _norm(row[0]) not in _CUSTOMER:
        return None
    if _norm(row[1]) not in _PRODUCT:
        return None
    months: List[Tuple[int, str, str, Optional[int]]] = []
    for idx, raw in enumerate(row):
        if idx < 2:
            continue
        spec = _month_spec(raw)
        if spec:
            key, label, year = spec
            months.append((idx, label, key, year))
            continue
        text = _norm(raw)
        if not text or text in _IGNORE or _SKIP_ROW.match(_cell(raw) or ""):
            continue
        return None
    if len(months) < 2:
        return None
    return {"customer_col": 0, "product_col": 1, "months": months}


def detect_matrix_month_layout(sheet: Sequence[Sequence[Any]]) -> bool:
    """True when Customer | Product | month columns, including Excel date headers."""
    if not sheet:
        return False
    limit = min(20, len(sheet))
    return any(_header_layout(sheet[idx]) for idx in range(limit))


def _find_header(matrix: Sequence[Sequence[Any]]) -> Tuple[int, Dict[str, Any]]:
    limit = min(20, len(matrix))
    for idx in range(limit):
        layout = _header_layout(matrix[idx])
        if layout:
            return idx, layout
    return -1, {}


def _period_for_month(key: str, year: Optional[int], fallback_fy: int) -> Tuple[str, Optional[str]]:
    month_num = month_number_from_key(key)
    if not month_num:
        return "", None
    if year:
        fy = fy_start_for_calendar_month(month_num, year)
        src = month_label(month_num, year)
    else:
        fy = fallback_fy
        cal_year = fy if month_num >= 4 else fy + 1
        src = month_label(month_num, cal_year)
    return quarter_label(fy, quarter_of_month(month_num)), src


def extract_matrix_month_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    distributor_label: str = "",
) -> Optional[Dict[str, Any]]:
    if not detect_matrix_month_layout(matrix):
        return None
    header_idx, layout = _find_header(matrix)
    if header_idx < 0:
        return None

    fallback_fy = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )
    months: List[Tuple[int, str, str, Optional[int]]] = layout["months"]
    rows: List[Dict[str, Any]] = []
    skipped_blank = 0
    skipped_total = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0
    short_months: List[str] = []

    for col, _label, key, year in months:
        month_num = month_number_from_key(key)
        if month_num:
            short = _SHORT[month_num]
            if short not in short_months:
                short_months.append(short)

    for row in matrix[header_idx + 1 :]:
        if not any(_cell(c) or isinstance(c, (int, float, Decimal, datetime, date)) for c in row):
            skipped_blank += 1
            continue
        customer = _cell(row[0]) if row else ""
        product = _cell(row[1]) if len(row) > 1 else ""
        if not customer and not product:
            skipped_blank += 1
            continue
        if _SKIP_ROW.match(customer) or _SKIP_ROW.match(product):
            skipped_total += 1
            continue
        if not customer or not product:
            skipped_blank += 1
            continue
        if _norm(customer) in _CUSTOMER or _norm(product) in _PRODUCT:
            continue
        for col, label, key, year in months:
            raw = row[col] if col < len(row) else None
            if raw is None or (_cell(raw) == "" and not isinstance(raw, (int, float, Decimal))):
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
            period, source_month = _period_for_month(key, year, fallback_fy)
            if not period:
                continue
            amount = Decimal(str(qty))
            payload: Dict[str, Any] = {
                "customer_name": customer,
                "product": product,
                "sales_quantity": amount,
                "sales_quantity_display": format_quantity(amount),
                "period": period,
                "reporting_quarter": period,
            }
            if source_month:
                payload["source_month"] = source_month
            rows.append(payload)
            qty_ok += 1

    periods = [str(row.get("period") or "") for row in rows if row.get("period")]
    quarter = ""
    if periods:
        ordered: List[str] = []
        for period in periods:
            if period not in ordered:
                ordered.append(period)
        quarter = ", ".join(format_period_display(period) for period in ordered)

    return {
        "rows": rows,
        "months_detected": short_months,
        "quarter": quarter,
        "distributor": (distributor_label or "").strip(),
        "skipped_blank": skipped_blank,
        "skipped_total": skipped_total,
        "skipped_invalid": skipped_invalid,
        "quantity_ok": qty_ok,
        "quantity_fail": qty_fail,
        "errors": [],
        "fiscal_year_start": fallback_fy,
        "header_row": header_idx + 1,
        "monthly_pivot": True,
        "layout": "matrix_month",
        "score": round(min(98.0, 80.0 + len(rows) * 0.25), 2),
        "detected": True,
        "llm_used": False,
    }


def extract_matrix_month_workbook(
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
        if not detect_matrix_month_layout(matrix):
            continue
        detected = True
        extracted = extract_matrix_month_rows(
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
            "layout": "matrix_month",
            "distributor": distributor_label,
            "quarter": "",
            "months_detected": [],
            "quantity_ok": 0,
            "quantity_fail": 0,
            "skipped_invalid": 0,
            "score": 0,
            "header_row": 1,
            "llm_used": False,
        }
    logger.info(
        "ERP Strategy : Matrix Month Parser\n"
        "Distributor : {}\n"
        "Rows Parsed : {}\n"
        "Months Detected : {}\n"
        "Quarter : {}\n"
        "LLM Used : False",
        best.get("distributor") or "",
        len(best.get("rows") or []),
        ", ".join(best.get("months_detected") or []),
        best.get("quarter") or "",
    )
    return best
