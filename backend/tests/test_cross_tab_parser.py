"""Cross-tab product×month ERP layout tests (EAST ARIEN-style)."""

from pathlib import Path

from openpyxl import Workbook

from app.erp_parser import ERPParserService
from app.erp_parser.cross_tab import detect_product_month_matrix
from app.erp_parser.workbook_detector import read_sheet_matrix


def _save(wb: Workbook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def test_product_month_matrix_extract(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # Merged-style product band (same label across month cols)
    ws.append([None, "APCOFLEX N1110", "APCOFLEX N1110", "APCOFLEX N1110", "APCOFLEX N745", "APCOFLEX N745", "APCOFLEX N745"])
    ws.append(["PARTICULARS", "Apr", "May", "Jun", "Apr", "May", "Jun"])
    ws.append(["Alpha Rubber", 10, 20, 30, 100, None, 50])
    ws.append(["Beta Works", None, None, 5, 7, 8, 9])
    ws.append(["TOTAL", 10, 20, 35, 107, 8, 59])
    path = _save(wb, tmp_path / "cross_tab.xlsx")

    matrix = read_sheet_matrix(path, "Sheet1")
    layout = detect_product_month_matrix(matrix)
    assert layout is not None
    assert len(layout["groups"]) == 2

    result = ERPParserService().parse_workbook(path, fiscal_year_start=2026, allow_llm_fallback=False)
    assert result.imported_rows >= 2
    alpha_n1110 = next(
        r
        for r in result.rows
        if r["customer_name"] == "Alpha Rubber" and r["product"] == "APCOFLEX N1110"
    )
    assert float(alpha_n1110["sales_quantity"]) == 60  # 10+20+30 as-is
    assert alpha_n1110.get("period") == "Q1 2026"
