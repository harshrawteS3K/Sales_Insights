"""Parser version labels stored with every successful ingestion."""

from __future__ import annotations

PARSER_VERSION = {
    "metadata": "v2.0",
    "stock_item_register": "v2.4",
    "product_blocks": "v2.2",
    "matrix_month": "v3.0",
    "cross_product_matrix": "v3.1",
    "product_month_matrix": "v2.1",
    "monthly_product_sheets": "v1.4",
    "header": "v1.3",
    "pdf_stock_register": "v1.0",
    "email_body_matrix": "v1.0",
}


def parser_version(parser_name: str) -> str:
    return PARSER_VERSION.get(parser_name or "", "v1.0")
