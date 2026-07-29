"""Column mapping and Excel structure validators."""

from typing import Dict, List, Sequence

import pandas as pd

from app.constants import (
    CUSTOMER_MASTER_REQUIRED_COLUMNS,
    PRODUCT_MASTER_REQUIRED_COLUMNS,
    SALES_REPORT_REQUIRED_COLUMNS,
)
from app.exceptions import ExcelProcessingError
from app.integrations.excel.headers import compact_header, normalize_header, resolve_sales_column_mapping


def map_columns(columns: Sequence[object], aliases: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Map canonical field names to actual DataFrame column names.

    Returns ``{canonical: actual_column_name}``.
    Matches on normalized and compacted header keys (handles spacing / pandas .1 suffixes).
    """
    normalized_lookup: Dict[str, str] = {}
    for col in columns:
        for key in (normalize_header(col), compact_header(col)):
            if key and key not in normalized_lookup:
                normalized_lookup[key] = str(col)

    mapping: Dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            for key in (normalize_header(alias), compact_header(alias)):
                if key in normalized_lookup:
                    mapping[canonical] = normalized_lookup[key]
                    break
            if canonical in mapping:
                break

    return mapping


def validate_required_mapping(
    mapping: Dict[str, str],
    required: Sequence[str],
    context: str,
) -> None:
    """Raise ExcelProcessingError when required columns are missing."""
    missing = [col for col in required if col not in mapping]
    if missing:
        raise ExcelProcessingError(
            f"{context}: missing required columns {missing}",
            details={"missing": missing, "mapped": mapping},
        )


def validate_sales_dataframe(df: pd.DataFrame) -> Dict[str, str]:
    """
    Validate and map sales report columns.

    Prefers official APCOTEX template mapping; falls back to aliases.
    Distributor may come from the header block (not required on the table).
    """
    if df is None or df.empty:
        raise ExcelProcessingError("Sales Excel is empty")
    mapping, _strategy, _official = resolve_sales_column_mapping(list(df.columns))
    if "distributor" not in mapping:
        return mapping
    validate_required_mapping(mapping, SALES_REPORT_REQUIRED_COLUMNS, "Sales report")
    return mapping


def validate_customer_master_dataframe(df: pd.DataFrame) -> Dict[str, str]:
    """Validate and map customer master columns (Phase 2: CUSTOMER NAME)."""
    if df is None or df.empty:
        raise ExcelProcessingError("Customer master Excel is empty")
    aliases = {
        "customer_name": [
            "customer name",
            "customer_name",
            "name of customer",
            "customer-name",
            "customer",
            "customername",
            "name",
        ],
        "customer_code": ["customer code", "customer_code", "code", "cust code"],
        "segment": ["segment", "application", "category"],
        "region": ["region"],
        "country": ["country"],
        "city": ["city"],
        "address": ["address"],
    }
    mapping = map_columns(list(df.columns), aliases)
    validate_required_mapping(mapping, CUSTOMER_MASTER_REQUIRED_COLUMNS, "Customer master")
    return mapping


def validate_product_master_dataframe(df: pd.DataFrame) -> Dict[str, str]:
    """
    Validate and map product master columns (single-table / legacy path).

    Prefer ``parse_product_master_workbook`` for production uploads — it supports
    multi-block APCOTEX layouts. This helper remains for simple DataFrame checks.
    """
    if df is None or df.empty:
        raise ExcelProcessingError("Product master Excel is empty")
    aliases = {
        "industry_type": [
            "industry type description",
            "industry type",
            "industry_type",
            "industry-type",
            "industrytypedescription",
            "type description",
            "industry",
        ],
        "product_code": [
            "product code",
            "product_code",
            "product-code",
            "productcode",
            "code",
            "sku",
            "product",
        ],
        "product_name": ["product name", "product_name", "name", "grade"],
        "segment": ["segment", "application", "category"],
        "description": ["description", "desc"],
        "unit": ["unit", "uom"],
    }
    mapping = map_columns(list(df.columns), aliases)
    # Legacy files used segment instead of industry type — accept as industry_type
    if "industry_type" not in mapping and "segment" in mapping:
        mapping["industry_type"] = mapping["segment"]
    validate_required_mapping(mapping, PRODUCT_MASTER_REQUIRED_COLUMNS, "Product master")
    return mapping
