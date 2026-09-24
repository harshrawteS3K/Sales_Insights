"""Repeating product-block ERP layout (BPS).

A product title sits on its own row. The next row is ``Party | Apr | May | Jun``.
Customer rows follow until TOTAL or the next product title. There is no Product column.
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
    source_month_label,
)
from app.erp_parser.header_mapper import is_month_header, normalize_header_text
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.utils.quantity import format_quantity, parse_quantity

logger = get_logger(__name__)

_PARTY_HEADERS = {"party", "party name"}
_TOTAL_RE = re.compile(r"^(grand\s+)?total\b", re.IGNORECASE)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return text


def _first_text(row: Sequence[Any]) -> Tuple[int, str]:
    for idx, raw in enumerate(row):
        text = _cell(raw)
        if text:
            return idx, text
    return -1, ""


def _is_party_header(row: Sequence[Any]) -> bool:
    idx, text = _first_text(row)
    if idx < 0:
        return False
    return normalize_header_text(text) in _PARTY_HEADERS


def _is_total_label(text: str) -> bool:
    return bool(_TOTAL_RE.match((text or "").strip()))


def _month_columns(row: Sequence[Any]) -> List[Tuple[int, str, str]]:
    found: List[Tuple[int, str, str]] = []
    for idx, raw in enumerate(row):
        if idx == 0:
            continue
        norm = normalize_header_text(raw)
        if not norm or not is_month_header(norm):
            continue
        key = re.sub(r"[\s\-_/']*\d{2,4}$", "", norm).strip() or norm
        found.append((idx, _cell(raw) or norm, key))
    return found


def _product_title_above(matrix: Sequence[Sequence[Any]], party_idx: int) -> str:
    for lookback in (1, 2):
        prev = party_idx - lookback
        if prev < 0:
            return ""
        idx, text = _first_text(matrix[prev])
        if not text:
            continue
        if _is_party_header(matrix[prev]) or _is_total_label(text):
            return ""
        if is_month_header(normalize_header_text(text)):
            return ""
        if idx > 0:
            return ""
        return re.sub(r"\s+", " ", text).strip()
    return ""


def detect_product_blocks(matrix: Sequence[Sequence[Any]]) -> bool:
    """True when the sheet repeats Product title + Party/month header blocks."""
    if not matrix:
        return False
    blocks = 0
    for idx, row in enumerate(matrix):
        if not _is_party_header(row):
            continue
        if len(_month_columns(row)) < 1:
            continue
        if _product_title_above(matrix, idx):
            blocks += 1
    return blocks >= 1


def extract_product_block_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Expand Party/month blocks into Customer / Product / Qty rows."""
    if not detect_product_blocks(matrix):
        return None

    fy_start = resolve_fy_start_year(
        fiscal_year_start=fiscal_year_start,
        reporting_quarter=reporting_quarter,
    )
    current_product = ""
    month_cols: List[Tuple[int, str, str]] = []
    rows: List[Dict[str, Any]] = []
    skipped_total = 0
    skipped_blank = 0
    skipped_invalid = 0
    qty_ok = 0
    qty_fail = 0

    for idx, row in enumerate(matrix):
        if _is_party_header(row):
            cols = _month_columns(row)
            title = _product_title_above(matrix, idx)
            if title and cols:
                current_product = title
                month_cols = cols
            continue

        label_idx, label = _first_text(row)
        if not label:
            skipped_blank += 1
            continue
        if _is_total_label(label):
            skipped_total += 1
            continue
        if not current_product or not month_cols or label_idx != 0:
            continue
        if is_month_header(normalize_header_text(label)):
            continue

        customer = re.sub(r"\s+", " ", label).strip()
        emitted = 0
        for col, header, key in month_cols:
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
            q_num = month_key_to_quarter(key)
            if not q_num:
                continue
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

    if not rows:
        return None

    return {
        "rows": rows,
        "skipped_total": skipped_total,
        "skipped_blank": skipped_blank,
        "skipped_invalid": skipped_invalid,
        "quantity_ok": qty_ok,
        "quantity_fail": qty_fail,
        "errors": [],
        "fiscal_year_start": fy_start,
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
    """Scan candidate sheets and return the block layout with the most rows."""
    file_path = Path(path)
    try:
        sheets = [sheet_name] if sheet_name else list_candidate_sheets(file_path)
    except Exception:  # noqa: BLE001
        return None

    best: Optional[Dict[str, Any]] = None
    best_sheet = ""
    for name in sheets:
        if not name:
            continue
        try:
            matrix = read_sheet_matrix(file_path, name)
        except Exception:  # noqa: BLE001
            continue
        extracted = extract_product_block_rows(
            matrix,
            fiscal_year_start=fiscal_year_start,
            reporting_quarter=reporting_quarter,
        )
        if not extracted or not extracted.get("rows"):
            continue
        if best is None or len(extracted["rows"]) > len(best["rows"]):
            best = extracted
            best_sheet = name
    if best is None:
        return None
    best["sheet_name"] = best_sheet
    logger.info(
        "ERP product blocks detected | sheet={} | rows={} | score={}",
        best_sheet,
        len(best["rows"]),
        best.get("score"),
    )
    return best
