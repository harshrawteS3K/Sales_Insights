"""Layout fingerprints. These hint at parsers; row confidence makes the choice."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from app.erp_parser.block_parser import detect_block_product_layout
from app.erp_parser.cross_product_matrix import detect_cross_product_matrix
from app.erp_parser.matrix_month_parser import detect_matrix_month_layout
from app.erp_parser.metadata_parser import detect_metadata_layout
from app.erp_parser.stock_item_parser import detect_stock_item_register


def fingerprint_sheet(matrix: Sequence[Sequence[Any]]) -> List[Dict[str, Any]]:
    """Return layout candidates. Distributor identity is not used."""
    found: List[Dict[str, Any]] = []
    if detect_metadata_layout(matrix):
        found.append(
            {
                "parser_name": "metadata",
                "layout": "Metadata Layout",
                "fingerprint_confidence": 90.0,
                "reason": "Sales Analysis, Item Group, and Account Name",
            }
        )
    if detect_stock_item_register(matrix):
        found.append(
            {
                "parser_name": "stock_item_register",
                "layout": "Stock Register",
                "fingerprint_confidence": 90.0,
                "reason": "Stock Item Register, Particulars, and Outwards",
            }
        )
    if detect_block_product_layout(matrix):
        found.append(
            {
                "parser_name": "product_blocks",
                "layout": "Block Layout",
                "fingerprint_confidence": 90.0,
                "reason": "Product title, Party, and TOTAL",
            }
        )
    if detect_cross_product_matrix(matrix):
        found.append(
            {
                "parser_name": "cross_product_matrix",
                "layout": "Cross Product Matrix",
                "fingerprint_confidence": 90.0,
                "reason": "Customer column, repeating month blocks, and product headers",
            }
        )
    if detect_matrix_month_layout(matrix):
        found.append(
            {
                "parser_name": "matrix_month",
                "layout": "Matrix Layout",
                "fingerprint_confidence": 90.0,
                "reason": "Customer, Product, and month columns",
            }
        )
    found.append(
        {
            "parser_name": "header",
            "layout": "Header Layout",
            "fingerprint_confidence": 50.0,
            "reason": "Customer, Product, and Qty columns",
        }
    )
    found.sort(key=lambda item: item["fingerprint_confidence"], reverse=True)
    return found
