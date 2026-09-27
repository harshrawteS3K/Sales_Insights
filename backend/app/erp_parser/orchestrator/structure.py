"""LLM returns a layout definition. Python extracts the sales rows."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from app.erp_parser.orchestrator.candidates import run_sheet_candidates
from app.erp_parser.orchestrator.types import ParserResult

STRUCTURE_PROMPT = """You are an ERP document structure analyzer.

You will receive a workbook fingerprint, sheet names, header cells, a merged-cell count, and at most 5 sample rows.
Do not extract customer rows. Do not extract product rows. Do not extract quantities. Do not rewrite cells.

Return JSON only:
{
  "layout_type": "cross_product_matrix",
  "customer_column": 0,
  "product_header_row": 1,
  "month_header_row": 0,
  "ignore_columns": ["Total"],
  "grouping": "horizontal_product_blocks",
  "parser_hint": "cross_product_matrix",
  "product_column": "",
  "quantity_column": "",
  "confidence": 0
}

layout_type must be one of: standard_header, matrix_month, cross_product_matrix, stock_item_register, metadata, product_blocks, unknown.
parser_hint must be one of: header, matrix_month, cross_product_matrix, stock_item_register, metadata, product_blocks.
Use null when a position is uncertain.
"""

_LAYOUT_PARSER = {
    "standard_header": "header",
    "header": "header",
    "matrix_month": "matrix_month",
    "matrix": "matrix_month",
    "matrix_monthly": "matrix_month",
    "cross_product_matrix": "cross_product_matrix",
    "matrix_cross": "cross_product_matrix",
    "stock_item_register": "stock_item_register",
    "stock_register": "stock_item_register",
    "metadata": "metadata",
    "sales_analysis": "metadata",
    "sales_analysis_metadata": "metadata",
    "product_blocks": "product_blocks",
    "block_product": "product_blocks",
}


def layout_parser_name(layout: Dict[str, Any]) -> str:
    raw = str(layout.get("layout_type") or layout.get("parser_hint") or "").strip().lower()
    raw = raw.replace(" ", "_").replace("-", "_")
    return _LAYOUT_PARSER.get(raw, "")


def extract_with_layout(
    sheet: Dict[str, Any],
    layout: Dict[str, Any],
    *,
    run_kwargs: Dict[str, Any],
    sheet_candidates: Sequence[ParserResult],
) -> Optional[ParserResult]:
    """Run the existing deterministic parser named by the layout JSON."""
    parser_name = layout_parser_name(layout)
    if not parser_name:
        hinted = str(layout.get("parser_hint") or "").strip()
        parser_name = hinted if hinted in _LAYOUT_PARSER.values() else ""
    if not parser_name:
        return None
    ready = next(
        (item for item in sheet_candidates if item.parser_name == parser_name and item.rows),
        None,
    )
    if ready is not None:
        ready.layout = str(layout.get("layout_type") or parser_name)
        return ready
    found = run_sheet_candidates(
        sheet["matrix"],
        sheet["sheet_name"],
        only=parser_name,
        **run_kwargs,
    )
    chosen = next((item for item in found if item.rows), None)
    if chosen is not None:
        chosen.layout = str(layout.get("layout_type") or parser_name)
    return chosen
