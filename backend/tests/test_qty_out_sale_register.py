"""Qty. Out transaction-register layout (Party Wise Sale Details)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from app.erp_parser import ERPParserService
from app.erp_parser.stock_item_parser import (
    detect_stock_item_register,
    extract_stock_item_rows,
)


def _bansal_style_workbook(path: Path) -> Path:
    """Exact structure: distributor, report title, product, Date/Type/Particulars/Qty In/Qty Out."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["BANSAL DYE CHEM PRIVATE LTD"])
    ws.append(["Some Address Line"])
    ws.append([])
    ws.append(["Party Wise Sale Details As per Purchase Quantity From April to June-26"])
    ws.append(["APCOTEX PT-800"])
    ws.append([])
    ws.append(
        [
            "Date",
            "Type",
            "Vch/Bill No",
            "Particulars",
            "Qty. In (Kg.)",
            "Qty. Out (Kg.)",
        ]
    )
    # Sale rows — quantity must come from Qty. Out, never Qty. In
    ws.append([date(2026, 4, 8), "Sale", "BDCPL-12", "ASN IMPEX", None, 5060])
    ws.append([date(2026, 4, 8), "Sale", "BDCPL-14", "KESHAV RESIN COATS PVT LTD", None, 440])
    ws.append([date(2026, 4, 8), "Sale", "BDCPL-15", "STICK PACK PVT.LTD", None, 2420])
    # Purchase must not become a sales record even if Qty. In is filled
    ws.append([date(2026, 4, 9), "Purc", "BDCPL-P1", "SUPPLIER X", 1000, None])
    # July must still parse (period validation is separate)
    ws.append([date(2026, 7, 2), "Sale", "BDCPL-40", "JULY CUSTOMER", None, 500])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def test_qty_out_sale_register_detects_and_maps(tmp_path: Path):
    path = _bansal_style_workbook(tmp_path / "SALE APCOTEX PT-800 APRIL TO JUNE-26.xlsx")
    from app.erp_parser.workbook_detector import read_sheet_matrix

    matrix = read_sheet_matrix(path, "Sheet1")
    assert detect_stock_item_register(matrix) is True

    extracted = extract_stock_item_rows(matrix)
    assert extracted is not None
    assert extracted["layout"] == "transaction_qty_out"
    assert extracted["distributor"] == "BANSAL DYE CHEM PRIVATE LTD"
    assert extracted["product"] == "APCOTEX PT-800"
    assert len(extracted["rows"]) == 4

    first = extracted["rows"][0]
    assert first["customer_name"] == "ASN IMPEX"
    assert first["product"] == "APCOTEX PT-800"
    assert first["sales_quantity"] == Decimal("5060")
    assert first["original_unit"] == "KG"
    assert first["source_month"] == "April 2026"

    customers = {row["customer_name"] for row in extracted["rows"]}
    assert "SUPPLIER X" not in customers
    assert "JULY CUSTOMER" in customers

    total = sum(Decimal(str(row["sales_quantity"])) for row in extracted["rows"])
    assert total == Decimal("8420")


def test_qty_out_sale_register_via_erp_parser(tmp_path: Path):
    path = _bansal_style_workbook(tmp_path / "bansal_qty_out.xlsx")
    result = ERPParserService().parse_workbook(
        path,
        distributor_label="BANSAL DYE CHEM PRIVATE LTD",
        allow_llm_fallback=False,
    )
    assert result.imported_rows == 4
    assert result.confidence_breakdown.get("layout") in {
        "transaction_qty_out",
        "stock_item_register",
        "Stock Register",
    } or (result.confidence_breakdown.get("parser_name") == "stock_item_register")
    assert float(result.rows[0]["sales_quantity"]) == 5060.0
    assert result.rows[0]["customer_name"] == "ASN IMPEX"
    assert result.rows[0]["product"] == "APCOTEX PT-800"
    assert result.rows[0].get("original_unit") == "KG"
    total = sum(float(r["sales_quantity"]) for r in result.rows)
    assert abs(total - 8420.0) < 0.001
    assert result.overall_confidence >= 75
    assert (result.confidence_breakdown or {}).get("layout") == "transaction_qty_out"
