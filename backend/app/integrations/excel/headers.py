"""
Unified header normalization and column mapping for APCOTEX Excel parsing.

Every parser component (template detection, distributor labels, sales mapping)
MUST use this module — one vocabulary, one normalizer, one mapper.
"""

from __future__ import annotations

import re
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from app.constants import SALES_REPORT_COLUMN_ALIASES, SALES_REPORT_TABLE_REQUIRED_COLUMNS
from app.exceptions import ExcelProcessingError

# ---------------------------------------------------------------------------
# Official APCOTEX Sales Insights Template (canonical contract)
# ---------------------------------------------------------------------------

OFFICIAL_TEMPLATE_NAME = "Official APCOTEX Template"

# Display labels as they appear on the official workbook (metadata block)
OFFICIAL_DISTRIBUTOR_LABELS: Dict[str, Tuple[str, ...]] = {
    "name": (
        "Name of Person",
        "Name of Distributor",
        "Distributor Name",
        "Distributor",
        "Person Name",
        "Representative Name",
    ),
    "company": (
        "Company Name",
        "Company",
    ),
    "address": (
        "Address",
    ),
    "phone": (
        "Phone No",
        "Phone Number",
        "Phone",
        "Ph",
        "Ph.",
        "Mobile",
    ),
    # Stored in reports.reporting_month; accepts quarters (Q1 2026) and legacy months
    "reporting_month": (
        "Reporting Quarter",
        "Reporting quarter",
        "REPORTING QUARTER",
        "Quarter",
        "Reporting Month",
        "Reporting month",
        "REPORTING MONTH",
        "Month",
        "Report Month",
        "Reporting Period",
        "Period",
    ),
}

# Official sales table headers (exact display forms → canonical field)
OFFICIAL_SALES_HEADERS: Dict[str, Tuple[str, ...]] = {
    "sr_no": ("Sr. No.", "Sr No", "Sr.No", "SR NO"),
    "customer_name": (
        "Customer Name",
        "Name of Customer",
        "Customer",
    ),
    "segment": ("Segment",),
    "product": (
        "Product",
        "Product (FG Code)",
        "Product FG Code",
        "FG Code",
    ),
    "quantity": (
        "Sales Quantity",
        "Quantity",
        "Qty",
    ),
    # Legacy optional columns (ignored if present; no longer generated)
    "opening_stock": ("Opening Stock", "Opening stock", "OPENING STOCK"),
    "closing_stock": ("Closing Stock", "Closing stock", "CLOSING STOCK"),
    "period": ("Period", "Reporting Period"),
}

# Minimum official sales columns required for an exact template match
OFFICIAL_SALES_REQUIRED = (
    "customer_name",
    "segment",
    "product",
    "quantity",
)


def normalize_header(value: object) -> str:
    """
    Intelligent header normalization (shared by all parser stages).

    - strip BOM / zero-width / non-breaking spaces
    - lowercase, trim
    - underscores / hyphens → spaces
    - strip punctuation (dots, colons, etc.)
    - collapse whitespace
    """
    text = str(value or "")
    text = (
        text.replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\u00a0", " ")
        .replace("\t", " ")
    )
    # Drop pandas duplicate-suffix noise: "Product Code.1" → "Product Code"
    text = re.sub(r"\.\d+$", "", text.strip())
    text = text.strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_header(value: object) -> str:
    """
    Fully compacted header key for alias matching.

    ``Industry Type Description`` → ``industrytypedescription``
    ``industry_type_description`` → ``industrytypedescription``
    """
    return re.sub(r"[^a-z0-9]", "", normalize_header(value))


def _alias_lookup(aliases: Mapping[str, Sequence[str]]) -> Dict[str, str]:
    """Build compact-alias → canonical field lookup (first wins per alias)."""
    lookup: Dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            for key in {normalize_header(alias), compact_header(alias)}:
                if key and key not in lookup:
                    lookup[key] = canonical
    return lookup


# Precomputed official lookups
_OFFICIAL_SALES_NORM: Dict[str, str] = _alias_lookup(OFFICIAL_SALES_HEADERS)
_OFFICIAL_DISTRIBUTOR_NORM: Dict[str, str] = _alias_lookup(OFFICIAL_DISTRIBUTOR_LABELS)

# Fallback vocabulary = expanded aliases from constants (includes official forms)
_FALLBACK_SALES_NORM: Dict[str, str] = _alias_lookup(SALES_REPORT_COLUMN_ALIASES)


def match_distributor_field(label: object) -> Optional[str]:
    """Map a distributor-block label to canonical field."""
    for key in (normalize_header(label), compact_header(label)):
        if key and key in _OFFICIAL_DISTRIBUTOR_NORM:
            return _OFFICIAL_DISTRIBUTOR_NORM[key]
    return None


def is_distributor_label(label: object) -> bool:
    """True when the cell is a known distributor-detail label."""
    return match_distributor_field(label) is not None


def is_sales_header_token(label: object) -> bool:
    """True when a token belongs to the unified sales header vocabulary."""
    for key in (normalize_header(label), compact_header(label)):
        if key and (key in _OFFICIAL_SALES_NORM or key in _FALLBACK_SALES_NORM):
            return True
    return False


def try_official_sales_mapping(columns: Sequence[object]) -> Optional[Dict[str, str]]:
    """
    Exact official-template mapping.

    Returns ``{canonical: actual_column}`` when all official required headers
    are present (by normalized equality). Returns None if not an official match.
    """
    normalized_to_actual: Dict[str, str] = {}
    for col in columns:
        key = normalize_header(col)
        if key and key not in normalized_to_actual:
            normalized_to_actual[key] = str(col).strip() if col is not None else ""

    mapping: Dict[str, str] = {}
    for canonical, display_forms in OFFICIAL_SALES_HEADERS.items():
        for form in display_forms:
            key = normalize_header(form)
            if key in normalized_to_actual:
                mapping[canonical] = normalized_to_actual[key]
                break

    if all(field in mapping for field in OFFICIAL_SALES_REQUIRED):
        return mapping
    return None


def map_sales_columns_fallback(columns: Sequence[object]) -> Dict[str, str]:
    """
    Alias-based fallback mapping using the unified vocabulary.

    Used only when the workbook is NOT an exact official template match.
    """
    normalized_to_actual: Dict[str, str] = {}
    for col in columns:
        key = normalize_header(col)
        if key and key not in normalized_to_actual:
            normalized_to_actual[key] = str(col).strip() if col is not None else ""

    mapping: Dict[str, str] = {}
    for canonical, alias_list in SALES_REPORT_COLUMN_ALIASES.items():
        for alias in alias_list:
            key = normalize_header(alias)
            if key in normalized_to_actual:
                mapping[canonical] = normalized_to_actual[key]
                break
    return mapping


def resolve_sales_column_mapping(
    columns: Sequence[object],
) -> Tuple[Dict[str, str], str, bool]:
    """
    Resolve sales column mapping with official-template priority.

    Returns ``(mapping, strategy, is_official)`` where strategy is one of:
    ``official_template``, ``alias_fallback``.

    Raises ExcelProcessingError when required sales columns cannot be mapped
    (fail-fast — never return a silent empty mapping).
    """
    official = try_official_sales_mapping(columns)
    if official is not None:
        return official, "official_template", True

    mapping = map_sales_columns_fallback(columns)
    missing = [c for c in SALES_REPORT_TABLE_REQUIRED_COLUMNS if c not in mapping]
    if missing:
        display = {
            "customer_name": "Customer Name",
            "segment": "Segment",
            "product": "Product",
            "quantity": "Sales Quantity",
        }
        missing_display = [display.get(m, m) for m in missing]
        raise ExcelProcessingError(
            "Official APCOTEX Template validation failed. "
            f"Missing column(s): {', '.join(missing_display)}",
            details={
                "missing": missing,
                "missing_display": missing_display,
                "columns": [str(c) for c in columns],
                "normalized": [normalize_header(c) for c in columns],
                "mapped": mapping,
            },
        )
    return mapping, "alias_fallback", False


def score_header_row(row: Sequence[object]) -> int:
    """Score how likely a row is the sales table header (unified vocabulary)."""
    tokens = {normalize_header(c) for c in row if c is not None and str(c).strip()}
    known = set(_OFFICIAL_SALES_NORM.keys()) | set(_FALLBACK_SALES_NORM.keys())
    return len(tokens & known)


def find_sales_header_row(raw_rows: List[List[object]]) -> Optional[int]:
    """Locate the sales header row using the unified vocabulary."""
    best_idx: Optional[int] = None
    best_score = 0
    for idx, row in enumerate(raw_rows):
        score = score_header_row(row)
        # Official table has 5–8 headers; require strong signal
        if score >= 4 and score > best_score:
            norms = {normalize_header(c) for c in row if c is not None}
            customer_like = any(
                t in norms
                for t in (
                    "name of customer",
                    "customer name",
                    "customer",
                    "buyer",
                    "buyer name",
                )
            )
            if customer_like or "product" in norms:
                best_idx = idx
                best_score = score
    return best_idx


# ---------------------------------------------------------------------------
# Product Master header vocabulary (Phase 2 + APCOTEX multi-block workbooks)
# ---------------------------------------------------------------------------

PRODUCT_MASTER_HEADER_ALIASES: Dict[str, Tuple[str, ...]] = {
    "industry_type": (
        "Industry Type Description",
        "Industry Type",
        "Industry",
        "Type Description",
        "industry_type",
        "industry type",
        "IndustryTypeDescription",
        "industry_type_description",
        "Industry-Type-Description",
        "INDUSTRY TYPE DESCRIPTION",
        "segment",  # legacy single-table uploads
        "application",
        "category",
    ),
    "product_code": (
        "Product Code",
        "Product",
        "ProductCode",
        "product_code",
        "product code",
        "Code",
        "SKU",
        "sku",
        "PRODUCT CODE",
        "Product-Code",
    ),
}

_PRODUCT_MASTER_NORM: Dict[str, str] = _alias_lookup(PRODUCT_MASTER_HEADER_ALIASES)


def match_product_master_field(label: object) -> Optional[str]:
    """Map a cell value to industry_type / product_code when it is a header alias."""
    for key in (normalize_header(label), compact_header(label)):
        if key and key in _PRODUCT_MASTER_NORM:
            return _PRODUCT_MASTER_NORM[key]
    return None
