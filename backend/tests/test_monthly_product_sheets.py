"""Monthly product-sheet ERP layout (NORTH CHOWDHRY-style)."""

from pathlib import Path

from openpyxl import Workbook

from app.erp_parser import ERPParserService
from app.erp_parser.monthly_product_sheets import (
    detect_monthly_product_sheets,
    extract_monthly_product_sheets,
    parse_sheet_month_label,
)


def _save(wb: Workbook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def test_parse_sheet_month_label():
    assert parse_sheet_month_label("Apr-25") == ("april", 2025)
    assert parse_sheet_month_label("Jan-26") == ("january", 2026)
    assert parse_sheet_month_label("Cover") is None


def test_monthly_product_sheets_extract(tmp_path: Path):
    wb = Workbook()
    apr = wb.active
    apr.title = "Apr-25"
    apr.append(["Company"])
    apr.append(["Report Apr-25"])
    apr.append(["Particulars", "APCOFLEX N745", "APCOFLEX N386", "Total"])
    apr.append(["Alpha Rubber", 100, 50, 150])
    apr.append(["Beta Works", 20, None, 20])
    apr.append(["TOTAL", 120, 50, 170])

    may = wb.create_sheet("May-25")
    may.append(["Company"])
    may.append(["Report May-25"])
    may.append(["Particulars", "APCOFLEX N745", "APCOFLEX N386", "Total"])
    may.append(["Alpha Rubber", 30, 10, 40])

    path = _save(wb, tmp_path / "chowdhry.xlsx")
    assert detect_monthly_product_sheets(path) is not None
    extracted = extract_monthly_product_sheets(path, fiscal_year_start=2025)
    assert extracted is not None
    assert extracted["layout"] == "monthly_product_sheets"
    assert len(extracted["rows"]) >= 3

    result = ERPParserService().parse_workbook(
        path, fiscal_year_start=2025, allow_llm_fallback=False
    )
    assert result.imported_rows >= 2
    alpha = next(
        r
        for r in result.rows
        if r["customer_name"] == "Alpha Rubber"
        and r["product"] == "APCOFLEX N745"
        and r.get("period") == "Q1 2025"
    )
    # Apr 100 + May 30 aggregated into one quarterly row
    assert float(alpha["sales_quantity"]) == 130

    # Unique customer×product×quarter keys (no duplicate hashes)
    keys = {
        (r["customer_name"], r["product"], r.get("period"))
        for r in result.rows
        if r.get("period") == "Q1 2025"
    }
    assert len(keys) == len(
        [r for r in result.rows if r.get("period") == "Q1 2025"]
    )
