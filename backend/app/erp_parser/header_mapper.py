"""Semantic header mapping via exact / synonym / RapidFuzz matching."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from app.erp_parser.header_dictionary import (
    get_header_dictionary,
    normalize_header_text,
)

# Re-export for callers (central normalization lives in header_dictionary)
__all__ = [
    "CANONICAL_FIELDS",
    "FIELD_DISPLAY",
    "MONTH_HEADERS",
    "NOISE_HEADERS",
    "best_field_match",
    "detect_month_columns",
    "is_month_header",
    "map_headers",
    "normalize_header_text",
]

# Canonical fields used by the ERP parser
CANONICAL_FIELDS = ("customer", "product", "quantity")

FIELD_DISPLAY = {
    "customer": "Customer Name",
    "product": "Product",
    "quantity": "Sales Quantity",
}

# Full + abbreviated month names (FY / calendar pivot ERPs)
MONTH_HEADERS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}

_MONTH_WITH_YEAR_RE = re.compile(
    r"^(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)"
    r"[\s\-_/']*\d{2,4}$",
    flags=re.IGNORECASE,
)

# Headers that look like titles / metadata — suppress as sales columns
NOISE_HEADERS = {
    "sr",
    "sr no",
    "sr. no",
    "sr. no.",
    "s no",
    "serial",
    "serial no",
    "sno",
    "#",
    "company",
    "company name",
    "distributor",
    "distributor name",
    "reporting quarter",
    "reporting month",
    "address",
    "phone",
    "phone no",
    "segment",
    "unit",
    "uom",
    "remarks",
    "remark",
    "date",
    "invoice",
    "invoice no",
    "invoice number",
    "customer code",
    "cust code",
    "party code",
    "account code",
    "total",
    "grand total",
    "opening",
    "closing",
    "opening balance",
    "closing balance",
    "voucher no",
    "vch type",
    "vch no",
    "balance",
    "rate",
    "amount",
}


def is_month_header(normalized_header: str) -> bool:
    """True when a header is a calendar/FY month label (optionally with year)."""
    if not normalized_header:
        return False
    if normalized_header in MONTH_HEADERS:
        return True
    return bool(_MONTH_WITH_YEAR_RE.match(normalized_header.replace(".", "")))


def detect_month_columns(headers: List[Any]) -> List[Tuple[int, str, str]]:
    """Return ``(0-based index, original label, month_key)`` for month quantity columns."""
    found: List[Tuple[int, str, str]] = []
    for idx, raw in enumerate(headers):
        norm = normalize_header_text(raw)
        if is_month_header(norm):
            label = str(raw).strip() if raw is not None else norm
            # Strip year suffix for quarter mapping: "april 25" → "april"
            key = re.sub(r"[\s\-_/']*\d{2,4}$", "", norm).strip() or norm
            found.append((idx, label, key))
    return found


def best_field_match(normalized_header: str, field: str) -> Tuple[str, float, str]:
    """
    Match one header against one canonical field.

    Matching order (input is already normalized centrally):
    1. Exact
    2. Case-insensitive (via normalize)
    3. Whitespace-normalized synonym containment
    4. RapidFuzz

    Returns ``(display_label, confidence_0_100, method)`` where method is
    exact | synonym | fuzzy | none.
    """
    label = FIELD_DISPLAY[field]
    if not normalized_header:
        return label, 0.0, "none"

    # Month columns are quantity sources, not customer/product labels
    if is_month_header(normalized_header):
        if field == "quantity":
            return label, 96.0, "month"
        return label, 0.0, "none"

    dictionary = get_header_dictionary()
    synonyms = dictionary.get_synonyms(field)

    # 1–2. Exact (case-insensitive + whitespace already applied by normalize)
    if normalized_header in synonyms or normalized_header == field:
        return label, 100.0, "exact"

    # 3. Synonym containment after whitespace normalization
    for syn in synonyms:
        if syn == normalized_header:
            return label, 98.0, "synonym"
        if syn in normalized_header or normalized_header in syn:
            ratio = len(syn) / max(len(normalized_header), 1)
            conf = 90.0 + min(8.0, ratio * 8.0)
            # Prefer "customer name" over "customer code"-like partials
            if field == "customer" and "code" in normalized_header and "name" not in normalized_header:
                conf = min(conf, 70.0)
            return label, round(conf, 1), "synonym"

    # 4. RapidFuzz against dictionary synonyms
    best_score = 0.0
    for syn in synonyms:
        score = float(fuzz.token_set_ratio(normalized_header, syn))
        score2 = float(fuzz.WRatio(normalized_header, syn))
        best_score = max(best_score, score, score2)

    if best_score >= 90:
        return label, round(best_score, 1), "fuzzy"
    if best_score >= 75:
        return label, round(best_score * 0.95, 1), "fuzzy"
    return label, 0.0, "none"


def map_headers(headers: List[Any]) -> Dict[str, Any]:
    """
    Map a header row to canonical fields.

    Supports monthly-pivot ERPs: when no single Qty column exists but month
    columns (APRIL…MARCH) are present, quantity is derived as the sum of those
    month columns.
    """
    normalized = [normalize_header_text(h) for h in headers]
    mapping: Dict[str, Optional[int]] = {"customer": None, "product": None, "quantity": None}
    originals: Dict[str, Optional[str]] = {"customer": None, "product": None, "quantity": None}
    confidences: Dict[str, float] = {"customer": 0.0, "product": 0.0, "quantity": 0.0}
    methods: Dict[str, str] = {"customer": "none", "product": "none", "quantity": "none"}

    # Score every (column, field) pair then greedily assign best unique columns
    candidates: List[Tuple[float, str, int, str, str]] = []
    for col_idx, norm in enumerate(normalized):
        if not norm or norm in NOISE_HEADERS:
            continue
        if is_month_header(norm):
            continue  # handled as quantity_columns below
        for field in CANONICAL_FIELDS:
            _label, score, method = best_field_match(norm, field)
            if score <= 0:
                continue
            raw = headers[col_idx]
            original = str(raw).strip() if raw is not None else ""
            candidates.append((score, field, col_idx, method, original))

    candidates.sort(key=lambda t: t[0], reverse=True)
    used_cols: set[int] = set()
    used_fields: set[str] = set()
    for score, field, col_idx, method, original in candidates:
        if field in used_fields or col_idx in used_cols:
            continue
        mapping[field] = col_idx
        originals[field] = original
        confidences[field] = score
        methods[field] = method
        used_fields.add(field)
        used_cols.add(col_idx)
        if len(used_fields) == 3:
            break

    month_cols = detect_month_columns(headers)
    quantity_columns = [idx for idx, _label, _key in month_cols]
    month_column_meta = [
        {"column": idx, "header": label, "month": key}
        for idx, label, key in month_cols
    ]

    # Monthly pivot: map quantity via month columns (split to FY quarters on extract)
    if mapping["quantity"] is None and quantity_columns:
        mapping["quantity"] = quantity_columns[0]
        originals["quantity"] = "Monthly columns → quarterly totals"
        confidences["quantity"] = 95.0
        methods["quantity"] = "monthly_sum"

    return {
        "positions": mapping,  # 0-based
        "originals": originals,
        "confidences": confidences,
        "methods": methods,
        "quantity_columns": quantity_columns if methods.get("quantity") == "monthly_sum" else [],
        "month_column_meta": month_column_meta if methods.get("quantity") == "monthly_sum" else [],
    }
