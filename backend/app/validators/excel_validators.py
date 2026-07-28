"""Column mapping and Excel structure validators."""

from typing import Dict, List, Sequence

import pandas as pd

from app.constants import (
    CUSTOMER_MASTER_REQUIRED_COLUMNS,
    PRODUCT_MASTER_REQUIRED_COLUMNS,
    SALES_REPORT_REQUIRED_COLUMNS,
)
from app.exceptions import ExcelProcessingError
from app.integrations.excel.headers import normalize_header, resolve_sales_column_mapping


def map_columns(columns: Sequence[object], aliases: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Map canonical field names to actual DataFrame column names.

    Returns ``{canonical: actual_column_name}``.
    Uses the unified header normalizer.
    """
    normalized_lookup = {normalize_header(col): col for col in columns}
    mapping: Dict[str, str] = {}

    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            key = normalize_header(alias)
            if key in normalized_lookup:
                mapping[canonical] = str(normalized_lookup[key])
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
    # Flat uploads that include a Distributor column still need it when no header block
    # — callers that have distributor details should use ExcelParserService.parse_sales_report.
    if "distributor" not in mapping:
        # Allow table-only validation without distributor (header-block templates)
        return mapping
    validate_required_mapping(mapping, SALES_REPORT_REQUIRED_COLUMNS, "Sales report")
    return mapping


def validate_customer_master_dataframe(df: pd.DataFrame) -> Dict[str, str]:
    """Validate and map customer master columns."""
    if df is None or df.empty:
        raise ExcelProcessingError("Customer master Excel is empty")
    aliases = {
        "customer_code": ["customer code", "customer_code", "code", "cust code"],
        "customer_name": [
            "customer name",
            "name of customer",
            "customer_name",
            "customer",
            "name",
        ],
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
    """Validate and map product master columns."""
    if df is None or df.empty:
        raise ExcelProcessingError("Product master Excel is empty")
    aliases = {
        "product_code": ["product code", "product_code", "code", "sku"],
        "product_name": ["product name", "product_name", "product", "name", "grade"],
        "segment": ["segment", "application", "category"],
        "description": ["description", "desc"],
        "unit": ["unit", "uom"],
    }
    mapping = map_columns(list(df.columns), aliases)
    validate_required_mapping(mapping, PRODUCT_MASTER_REQUIRED_COLUMNS, "Product master")
    return mapping
