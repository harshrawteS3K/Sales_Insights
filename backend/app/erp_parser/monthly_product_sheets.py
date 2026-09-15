"""Multi-sheet monthly product matrix (e.g. NORTH CHOWDHRY RUBBER).

Each sheet is one month (Apr-25, May-25, …). Header row::

    Particulars | PRODUCT A | PRODUCT B | … | Total

Data rows::

    Customer name | qty | qty | … | row total

We emit Customer × Product × Qty rows tagged with the sheet's FY quarter.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from app.core.logging import get_logger
from app.erp_parser.fiscal_quarters import (
    month_key_to_quarter,
    quarter_label,
    resolve_fy_start_year,
)
from app.erp_parser.header_mapper import (
    NOISE_HEADERS,
    best_field_match,
    is_month_header,
    normalize_header_text,
)
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.utils.quantity import format_quantity, parse_quantity

logger = get_logger(__name__)

_SHEET_MONTH_RE = re.compile(
    r"^(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)"
    r"[\s\-_/']*(\d{2,4})$",
    flags=re.IGNORECASE,
)

_MONTH_ALIASES = {
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

_STUB = {
    "particulars",
    "particular",
    "customer",
    "customer name",
    "party",
    "party name",
    "buyer",
    "dealer",
    "name",
}

_TOTAL_RE = re.compile(
    r"^\s*(grand\s*)?total\b|\bsub\s*total\b|\btotals?\b",
    flags=re.IGNORECASE,
)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("_x000D_", " ").replace("\n", " ").strip()


def parse_sheet_month_label(name: str) -> Optional[Tuple[str, int]]:
    """``Apr-25`` → ``('april', 2025)``."""
    text = (name or "").strip()
    compact = re.sub(r"\s+", "", text)
    match = _SHEET_MONTH_RE.match(compact)
    if not match:
        match = _SHEET_MONTH_RE.match(re.sub(r"\s+", "-", text))
    if not match:
        return None
    mon = _MONTH_ALIASES.get(match.group(1).lower())
    if not mon:
        return None
    year = int(match.group(2))
    if year < 100:
        year += 2000
    return mon, year


def _looks_like_product(raw: Any) -> bool:
    text = _cell(raw)
    if not text or len(text) < 2:
        return False
    norm = normalize_header_text(text)
    if not norm or norm in NOISE_HEADERS or norm in _STUB:
        return False
    if is_month_header(norm):
        return False
    if norm in {"total", "total qty", "qty", "quantity", "sr", "sr no"}:
        return False
    if norm.startswith("total"):
        return False
    return True


def _find_product_header_row(matrix: Sequence[Sequence[Any]]) -> Optional[Dict[str, Any]]:
    """Locate Particulars + product columns within the first 15 rows."""
    limit = min(15, len(matrix))
    best = None
    best_score = 0.0
    for idx in range(limit):
        row = list(matrix[idx])
        if not row:
            continue
        stub = normalize_header_text(row[0] if row else "")
        stub_ok = stub in _STUB or best_field_match(stub, "customer")[1] >= 85
        if not stub_ok:
            continue
        products: List[Tuple[int, str]] = []
        for c in range(1, len(row)):
            raw = row[c]
            norm = normalize_header_text(raw)
            if not norm or norm.startswith("total"):
                continue
            if _looks_like_product(raw):
                products.append((c, _cell(raw)))
        if len(products) < 2:
            continue
        score = 50.0 + min(40.0, len(products) * 3.0)
        if score > best_score:
            best_score = score
            best = {
                "header_row_index": idx,
                "customer_col": 0,
                "products": products,
                "score": score,
            }
    return best


def detect_monthly_product_sheets(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """True when workbook has several month-named sheets with product columns."""
    file_path = Path(path)
    sheets = list_candidate_sheets(file_path) or []
    month_sheets: List[Tuple[str, str, int]] = []
    for name in sheets:
        parsed = parse_sheet_month_label(name)
        if parsed:
            month_sheets.append((name, parsed[0], parsed[1]))
    if len(month_sheets) < 2:
        return None

    probe_name = month_sheets[0][0]
    matrix = read_sheet_matrix(file_path, probe_name)
    header = _find_product_header_row(matrix)
    if not header:
        return None

    return {
        "layout": "monthly_product_sheets",
        "sheets": month_sheets,
        "probe_header": header,
        "score": round(60.0 + min(30.0, len(month_sheets) * 2.5), 2),
    }


def extract_monthly_product_sheets(
    path: Union[str, Path],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Extract all month sheets into Customer/Product/Qty quarterly rows."""
    meta = detect_monthly_product_sheets(path)
    if not meta:
        return None

    file_path = Path(path)
    fy_start = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )

    # Sum Apr+May+Jun (etc.) into one Customer×Product×Quarter row.
    # Without this, identical qty across months collide on row_hash at import.
    buckets: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    skipped_total = 0
    skipped_blank = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0
    errors: List[str] = []
    sheets_used: List[str] = []

    for sheet_name, month_key, cal_year in meta["sheets"]:
        q_num = month_key_to_quarter(month_key)
        if not q_num:
            continue
        sheet_fy = cal_year if q_num != 4 else cal_year - 1
        label_fy = int(fiscal_year_start) if fiscal_year_start else sheet_fy
        period = quarter_label(label_fy, q_num)

        matrix = read_sheet_matrix(file_path, sheet_name)
        header = _find_product_header_row(matrix)
        if not header:
            errors.append(f"Sheet {sheet_name}: no product header")
            continue
        sheets_used.append(sheet_name)
        header_idx = int(header["header_row_index"])
        customer_col = int(header["customer_col"])
        products: List[Tuple[int, str]] = list(header["products"])

        for abs_idx, row in enumerate(matrix[header_idx + 1 :], start=header_idx + 2):
            if not any(_cell(c) for c in row):
                skipped_blank += 1
                continue
            if any(_TOTAL_RE.search(_cell(c) or "") for c in row if _cell(c)):
                skipped_total += 1
                continue
            customer = _cell(row[customer_col] if customer_col < len(row) else None)
            if not customer:
                skipped_blank += 1
                continue
            customer = re.sub(r"\s+", " ", customer).strip()

            emitted = 0
            for col, product in products:
                raw = row[col] if col < len(row) else None
                if raw is None or _cell(raw) == "":
                    continue
                try:
                    qty, _disp = parse_quantity(raw)
                except ValueError:
                    qty_fail += 1
                    continue
                if qty == 0:
                    continue
                if qty < 0:
                    skipped_invalid += 1
                    continue
                key = (customer.casefold(), product.casefold(), period.casefold())
                if key in buckets:
                    buckets[key]["sales_quantity"] = (
                        Decimal(str(buckets[key]["sales_quantity"])) + Decimal(str(qty))
                    )
                else:
                    buckets[key] = {
                        "customer_name": customer,
                        "product": product,
                        "sales_quantity": Decimal(str(qty)),
                        "period": period,
                        "reporting_quarter": period,
                    }
                qty_ok += 1
                emitted += 1
            if emitted == 0:
                skipped_blank += 1

    rows: List[Dict[str, Any]] = []
    for item in buckets.values():
        qty = Decimal(str(item["sales_quantity"]))
        rows.append(
            {
                **item,
                "sales_quantity": qty,
                "sales_quantity_display": format_quantity(qty),
            }
        )

    if not rows:
        return None

    logger.info(
        "Monthly product sheets extracted | sheets={} | rows={} (quarterly aggregated)",
        len(sheets_used),
        len(rows),
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
        "monthly_pivot": True,
        "layout": "monthly_product_sheets",
        "sheets_used": sheets_used,
        "score": meta["score"],
    }
