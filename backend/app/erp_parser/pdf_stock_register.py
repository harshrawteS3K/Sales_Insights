"""Hierarchical PDF stock register (Purandar).

Customer totals introduce a name. Dated lines under that name are the sales
rows. Customer total lines are not imported.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from app.erp_parser.stock_item_parser import _as_date, _period_for_date, detect_stock_item_register
from app.core.logging import get_logger
from app.utils.period_calendar import month_label
from app.utils.quantity import format_quantity, parse_quantity

logger = get_logger(__name__)

_MONTH = r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_DATE = rf"\d{{1,2}}[-/\s.](?:{_MONTH})[a-z]*[-/\s.]\d{{2,4}}"
_DATE_START_RE = re.compile(rf"^(?P<date>{_DATE})\b", re.IGNORECASE)
_CUSTOMER_RE = re.compile(
    rf"^(?P<name>.+?)\s+(?P<qty>\d[\d,]*(?:\.\d+)?)\s*kgs?\.?\s*$",
    re.IGNORECASE,
)
_PRODUCT_RE = re.compile(
    r"(?P<product>Apcotex\b.*?)(?=\s+(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*kgs?\.?)?\s*$)",
    re.IGNORECASE,
)
_QTY_RE = re.compile(
    r"(?P<qty>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*kgs?\.?)?\s*$",
    re.IGNORECASE,
)
_SKIP_NAME_RE = re.compile(r"^(grand\s+|sub\s+)?totals?\b", re.IGNORECASE)


def _parse_kg(raw: str) -> Optional[Decimal]:
    """Kilograms from ``1000 Kgs.``, ``1,250 KG``, ``225.50``, or ``750``."""
    text = re.sub(r"\s+", " ", str(raw or "")).strip()
    text = re.sub(r"\s*kgs?\.?\s*$", "", text, flags=re.IGNORECASE).strip()
    text = text.replace(",", "")
    if not text:
        return None
    try:
        amount, _display = parse_quantity(text)
    except (ValueError, ArithmeticError):
        return None
    if amount <= 0:
        return None
    return Decimal(str(amount))


def _line(row: Sequence[Any]) -> str:
    parts: List[str] = []
    for cell in row:
        if cell is None:
            continue
        text = str(cell).replace("\n", " ").strip()
        if not text or text.lower() in {"nan", "none"}:
            continue
        parts.append(re.sub(r"\s+", " ", text))
    return " ".join(parts).strip()


def _customer_name(line: str) -> str:
    if _DATE_START_RE.match(line) or re.search(r"\bapcotex\b", line, re.IGNORECASE):
        return ""
    match = _CUSTOMER_RE.match(line)
    if not match:
        return ""
    name = re.sub(r"\s+", " ", match.group("name")).strip()
    if not name or _SKIP_NAME_RE.match(name):
        return ""
    return name


def _transaction(line: str) -> Optional[Dict[str, str]]:
    if not _DATE_START_RE.match(line):
        return None
    product = _PRODUCT_RE.search(line)
    quantity = _QTY_RE.search(line)
    dated = _DATE_START_RE.match(line)
    if not product or not quantity or not dated:
        return None
    return {
        "date": dated.group("date"),
        "product": re.sub(r"\s+", " ", product.group("product")).strip(),
        "quantity": quantity.group(0).strip(),
    }


def looks_like_pdf_stock_register(lines: Sequence[str]) -> bool:
    """True when customer totals and dated Apcotex lines are both present."""
    headers = 0
    transactions = 0
    for line in lines:
        text = re.sub(r"\s+", " ", str(line or "")).strip()
        if not text:
            continue
        if _customer_name(text):
            headers += 1
        elif _transaction(text):
            transactions += 1
    return headers >= 1 and transactions >= 1


def _tabular_header(matrix: Sequence[Sequence[Any]]) -> bool:
    """Leave a real Customer / Product / Quantity sheet to the Excel parsers."""
    from app.erp_parser.header_detector import detect_header_row

    found = detect_header_row(matrix)
    positions = (found.get("mapping") or {}).get("positions") or {}
    mapped = all(positions.get(field) is not None for field in ("customer", "product", "quantity"))
    return bool(mapped and float(found.get("header_score") or 0) >= 50)


def extract_pdf_stock_register_rows(
    matrix: Sequence[Sequence[Any]],
    *,
    fiscal_year_start: Optional[int] = None,
    reporting_quarter: Optional[str] = None,
    distributor_label: str = "",
) -> Optional[Dict[str, Any]]:
    del fiscal_year_start, reporting_quarter
    if not matrix:
        return None
    lines = [_line(row) for row in matrix]
    headers = [name for name in (_customer_name(line) for line in lines) if name]
    transactions = [item for item in (_transaction(line) for line in lines) if item]
    if not headers or not transactions:
        return None
    if detect_stock_item_register(matrix) or _tabular_header(matrix):
        return None

    rows: List[Dict[str, Any]] = []
    customers: List[str] = []
    current = ""
    for line in lines:
        header = _customer_name(line)
        if header:
            current = header
            if header not in customers:
                customers.append(header)
            continue
        item = _transaction(line)
        if not item or not current:
            continue
        tx_date = _as_date(item["date"])
        if tx_date is None:
            logger.warning("PDF stock register date skipped | line={}", line)
            continue
        raw_quantity = item["quantity"]
        amount = _parse_kg(raw_quantity)
        if amount is None:
            logger.warning(
                "PDF stock register quantity not parsed | line={} | raw={!r}",
                line,
                raw_quantity,
            )
            continue
        period = _period_for_date(tx_date)
        sales_qty = float(amount)
        logger.info(
            "Raw Line:\n{}\n\nRaw Quantity:\n\"{}\"\n\nParsed KG:\n{}\n\nMapped sales_qty:\n{}",
            line,
            raw_quantity,
            sales_qty,
            sales_qty,
        )
        rows.append(
            {
                "customer_name": current,
                "product": item["product"],
                "sales_quantity": amount,
                "quantity": amount,
                "sales_qty": amount,
                "sales_quantity_display": format_quantity(amount),
                "period": period,
                "reporting_quarter": period,
                "source_month": month_label(tx_date.month, tx_date.year),
                "transaction_date": tx_date.isoformat(),
                "original_unit": "KG",
            }
        )

    if not rows:
        return None

    periods = [str(row.get("period") or "") for row in rows if row.get("period")]
    return {
        "rows": rows,
        "customers_detected": len(customers),
        "products": sorted({str(row["product"]) for row in rows}),
        "distributor": (distributor_label or "").strip(),
        "quarter": periods[0] if periods else "",
        "quantity_ok": len(rows),
        "quantity_fail": 0,
        "skipped_invalid": 0,
        "header_row": 1,
        "monthly_pivot": False,
        "layout": "pdf_stock_register",
        "score": 98.0,
        "detected": True,
    }
