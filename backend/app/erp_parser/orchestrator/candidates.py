"""Run every existing ERP parser and return a scored ParserResult.

Extractors are unchanged. A candidate that finds nothing scores zero and
does not stop the other candidates.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from app.erp_parser.block_parser import extract_product_block_rows
from app.erp_parser.cross_product_matrix import extract_cross_product_rows
from app.erp_parser.cross_tab import (
    detect_product_month_matrix,
    extract_product_month_matrix_rows,
)
from app.erp_parser.header_detector import detect_header_row
from app.erp_parser.matrix_month_parser import extract_matrix_month_rows
from app.erp_parser.metadata_parser import extract_metadata_rows
from app.erp_parser.monthly_product_sheets import extract_monthly_product_sheets
from app.erp_parser.orchestrator.types import ParserResult
from app.erp_parser.row_extractor import extract_rows
from app.erp_parser.stock_item_parser import extract_stock_item_rows

PARSER_LABEL = {
    "metadata": "Metadata Parser",
    "stock_item_register": "Stock Item Register Parser",
    "product_blocks": "Block Product Parser",
    "matrix_month": "Matrix Month Parser",
    "cross_product_matrix": "Cross Product Matrix",
    "header": "Header Parser",
    "product_month_matrix": "Cross Tab Parser",
    "monthly_product_sheets": "Monthly Product Sheets",
}

# Tie-break only. The weighted score still decides the winner.
PRIORITY = {
    "metadata": 6,
    "stock_item_register": 5,
    "product_blocks": 4,
    "matrix_month": 3,
    "cross_product_matrix": 3,
    "product_month_matrix": 2,
    "monthly_product_sheets": 1,
    "header": 0,
}


def _mapped(
    *,
    customer: Optional[int],
    product: Optional[int],
    quantity: Optional[int],
    originals: Dict[str, str],
    method: str,
    field_conf: Dict[str, float],
) -> Dict[str, Any]:
    return {
        "positions": {"customer": customer, "product": product, "quantity": quantity},
        "originals": originals,
        "confidences": field_conf,
        "methods": {"customer": method, "product": method, "quantity": method},
        "quantity_columns": [],
        "month_column_meta": [],
    }


def _result(
    name: str,
    extracted: Optional[Dict[str, Any]],
    mapped: Dict[str, Any],
    *,
    sheet_name: str,
    reason: str,
) -> ParserResult:
    rows = list((extracted or {}).get("rows") or [])
    return ParserResult(
        rows=rows,
        parser_name=name,
        reason=reason if rows else f"{reason} produced no rows",
        extracted=extracted or {},
        mapped=mapped,
        sheet_name=sheet_name,
        header_row=int((extracted or {}).get("header_row") or 1),
        sheet_score=float((extracted or {}).get("score") or 0),
    )


def _guard(name: str, sheet_name: str, fn: Callable[[], ParserResult]) -> ParserResult:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return ParserResult(
            parser_name=name,
            sheet_name=sheet_name,
            reason=f"{PARSER_LABEL.get(name, name)} failed: {exc}",
            warnings=[str(exc)],
        )


def run_metadata(matrix: Sequence[Sequence[Any]], sheet_name: str, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        extracted = extract_metadata_rows(
            matrix,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
        )
        field_conf = {"customer": 98.0, "product": 98.0, "quantity": 96.0}
        return _result(
            "metadata",
            extracted,
            _mapped(
                customer=0,
                product=None,
                quantity=1,
                originals={
                    "customer": "Account Name",
                    "product": "Item Group",
                    "quantity": "Nett Sale Qty.",
                },
                method="metadata",
                field_conf=field_conf,
            ),
            sheet_name=sheet_name,
            reason="Sales Analysis, Item Group, and Account Name",
        )

    return _guard("metadata", sheet_name, _run)


def run_stock(matrix: Sequence[Sequence[Any]], sheet_name: str, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        extracted = extract_stock_item_rows(
            matrix,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
            distributor_label=kwargs.get("distributor_label") or "",
        )
        field_conf = {"customer": 97.0, "product": 97.0, "quantity": 96.0}
        return _result(
            "stock_item_register",
            extracted,
            _mapped(
                customer=1,
                product=None,
                quantity=None,
                originals={
                    "customer": "Particulars",
                    "product": "Stock Item Register title",
                    "quantity": "Outwards Quantity",
                },
                method="stock_item_register",
                field_conf=field_conf,
            ),
            sheet_name=sheet_name,
            reason="Stock Item Register, Particulars, and Outwards",
        )

    return _guard("stock_item_register", sheet_name, _run)


def run_blocks(matrix: Sequence[Sequence[Any]], sheet_name: str, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        extracted = extract_product_block_rows(
            matrix,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
        )
        field_conf = {"customer": 97.0, "product": 97.0, "quantity": 95.0}
        return _result(
            "product_blocks",
            extracted,
            _mapped(
                customer=0,
                product=None,
                quantity=None,
                originals={
                    "customer": "Party",
                    "product": "Product title",
                    "quantity": "Month columns",
                },
                method="product_blocks",
                field_conf=field_conf,
            ),
            sheet_name=sheet_name,
            reason="Product title, Party, and month columns",
        )

    return _guard("product_blocks", sheet_name, _run)


def run_matrix(matrix: Sequence[Sequence[Any]], sheet_name: str, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        extracted = extract_matrix_month_rows(
            matrix,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
            distributor_label=kwargs.get("distributor_label") or "",
        )
        field_conf = {"customer": 98.0, "product": 98.0, "quantity": 96.0}
        return _result(
            "matrix_month",
            extracted,
            _mapped(
                customer=0,
                product=1,
                quantity=None,
                originals={
                    "customer": "Customer",
                    "product": "Product",
                    "quantity": "Month columns",
                },
                method="matrix_month",
                field_conf=field_conf,
            ),
            sheet_name=sheet_name,
            reason="Customer, Product, and month columns",
        )

    return _guard("matrix_month", sheet_name, _run)


def run_header(matrix: Sequence[Sequence[Any]], sheet_name: str, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        from app.erp_parser.parser_service import _mapping_complete

        info = detect_header_row(matrix)
        mapped = info["mapping"]
        positions = dict(mapped["positions"])
        qty_cols = list(mapped.get("quantity_columns") or [])
        if not _mapping_complete(positions, qty_cols):
            return ParserResult(
                parser_name="header",
                sheet_name=sheet_name,
                reason="Header Parser could not map Customer, Product, and Quantity",
                mapped=mapped,
                header_row=int(info.get("header_row") or 1),
            )
        extracted = extract_rows(
            matrix,
            header_row_index=int(info["header_row_index"]),
            positions=positions,
            quantity_columns=qty_cols or None,
            month_column_meta=list(mapped.get("month_column_meta") or []) or None,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
        )
        extracted["header_row"] = info.get("header_row") or 1
        extracted["layout"] = extracted.get("layout") or "header"
        extracted["score"] = float(info.get("header_score") or 0)
        return _result(
            "header",
            extracted,
            mapped,
            sheet_name=sheet_name,
            reason="Customer, Product, and Qty columns",
        )

    return _guard("header", sheet_name, _run)


def run_cross_product(matrix: Sequence[Sequence[Any]], sheet_name: str, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        extracted = extract_cross_product_rows(
            matrix,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
            distributor_label=kwargs.get("distributor_label") or "",
        )
        confidence = float((extracted or {}).get("confidence") or 0)
        field_conf = {"customer": 98.0, "product": 98.0, "quantity": 96.0}
        result = _result(
            "cross_product_matrix",
            extracted,
            _mapped(
                customer=0,
                product=None,
                quantity=None,
                originals={
                    "customer": "Customer",
                    "product": "Product block",
                    "quantity": "Month columns",
                },
                method="cross_product_matrix",
                field_conf=field_conf,
            ),
            sheet_name=sheet_name,
            reason="Customer column, repeating month blocks, and product headers",
        )
        result.confidence = confidence
        return result

    return _guard("cross_product_matrix", sheet_name, _run)


def run_cross_tab(matrix: Sequence[Sequence[Any]], sheet_name: str, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        layout = detect_product_month_matrix(matrix)
        if not layout:
            return ParserResult(
                parser_name="product_month_matrix",
                sheet_name=sheet_name,
                reason="Cross tab layout not detected",
            )
        extracted = extract_product_month_matrix_rows(
            matrix,
            layout=layout,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
        )
        extracted["score"] = float(layout.get("score") or 0)
        extracted["header_row"] = int(layout.get("header_row") or 1)
        field_conf = {"customer": 95.0, "product": 95.0, "quantity": 92.0}
        mapped = _mapped(
            customer=int(layout["customer_col"]),
            product=None,
            quantity=None,
            originals={
                "customer": "PARTICULARS / Customer",
                "product": "Product column groups",
                "quantity": "Monthly columns",
            },
            method="cross_tab",
            field_conf=field_conf,
        )
        return _result(
            "product_month_matrix",
            extracted,
            mapped,
            sheet_name=sheet_name,
            reason="Product groups and month columns",
        )

    return _guard("product_month_matrix", sheet_name, _run)


def run_monthly_sheets(path: Any, **kwargs: Any) -> ParserResult:
    def _run() -> ParserResult:
        extracted = extract_monthly_product_sheets(
            path,
            fiscal_year_start=kwargs.get("fiscal_year_start"),
            reporting_quarter=kwargs.get("reporting_quarter"),
        )
        sheets = list((extracted or {}).get("sheets_used") or [])
        field_conf = {"customer": 96.0, "product": 96.0, "quantity": 94.0}
        mapped = _mapped(
            customer=0,
            product=None,
            quantity=None,
            originals={
                "customer": "Particulars",
                "product": "Product columns per month sheet",
                "quantity": "Month sheets",
            },
            method="monthly_sheets",
            field_conf=field_conf,
        )
        result = _result(
            "monthly_product_sheets",
            extracted,
            mapped,
            sheet_name=sheets[0] if sheets else "",
            reason="One worksheet per month",
        )
        if sheets:
            result.warnings.append("sheets=" + ", ".join(sheets))
        return result

    return _guard("monthly_product_sheets", "", _run)


_SHEET_RUNNERS = {
    "metadata": run_metadata,
    "stock_item_register": run_stock,
    "product_blocks": run_blocks,
    "matrix_month": run_matrix,
    "cross_product_matrix": run_cross_product,
    "header": run_header,
    "product_month_matrix": run_cross_tab,
}


def run_sheet_candidates(
    matrix: Sequence[Sequence[Any]],
    sheet_name: str,
    *,
    only: Optional[str] = None,
    **kwargs: Any,
) -> List[ParserResult]:
    names = [only] if only in _SHEET_RUNNERS else list(_SHEET_RUNNERS)
    return [_SHEET_RUNNERS[name](matrix, sheet_name, **kwargs) for name in names]
