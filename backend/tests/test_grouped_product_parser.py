"""Grouped PRODUCT: sections with Customer, Doc Date, and Quantity."""

from datetime import date
from pathlib import Path

from app.erp_parser.grouped_product_parser import (
    detect_grouped_product_layout,
    extract_grouped_product_rows,
)
from app.erp_parser.parser_service import ERPParserService

_WORKBOOK = Path(__file__).resolve().parents[1] / (
    "uploads/attachments/267928e399194d00bf6c07224975e633_"
    "APCOTEX SALE (26-27) UPTO 31.08.26 DETAIL.xlsx"
)


def _qty(rows, needle: str) -> float:
    return float(
        sum(row["sales_quantity"] for row in rows if needle in str(row["product"]).upper())
    )


def test_real_grouped_product_workbook_skips_llm():
    result = ERPParserService().parse_workbook(_WORKBOOK, allow_llm_fallback=True)
    breakdown = result.confidence_breakdown or {}
    rows = result.rows
    assert breakdown.get("parser_name") == "grouped_product_transactions"
    assert breakdown.get("llm_used") is False
    assert float(result.overall_confidence) >= 90
    assert result.confidence_band == "green"
    assert rows
    assert all(row.get("original_unit") == "KG" for row in rows)
    assert all(row.get("customer_name") for row in rows)
    assert all(row.get("transaction_date") for row in rows)
    assert all(row.get("product") for row in rows)
    assert not any(str(row["customer_name"]).lower().startswith("total") for row in rows)
    assert not any("grand" in str(row["customer_name"]).lower() for row in rows)
    total = float(sum(row["sales_quantity"] for row in rows))
    assert abs(total - 54325) < 0.001
    assert abs(_qty(rows, "SR-558") - 15700) < 0.001
    assert abs(_qty(rows, "SR-568") - 38625) < 0.001
    q1 = [row for row in rows if "Q1" in str(row.get("period"))]
    q2 = [row for row in rows if "Q2" in str(row.get("period"))]
    assert q1 and q2
    assert all(date.fromisoformat(row["transaction_date"]).month in (4, 5, 6) for row in q1)
    assert all(date.fromisoformat(row["transaction_date"]).month in (7, 8, 9) for row in q2)


def test_additional_product_sections_are_dynamic():
    matrix = [
        ["Title"],
        ["S.N", "CUSTOMER", "DOC DATE", "QUANTITY (KG)"],
        [None, "PRODUCT: ALPHA-1", None, None],
        ["1", "Acme", date(2026, 4, 2), 10],
        [None, "Totals", None, 10],
        [None, "PRODUCT: BETA-9", None, None],
        ["1", "North", date(2026, 10, 5), 25],
        [None, "Grand Totals", "35", 35],
    ]
    assert detect_grouped_product_layout(matrix)
    extracted = extract_grouped_product_rows(matrix)
    rows = extracted["rows"]
    assert extracted["llm_used"] is False
    assert extracted["confidence"] >= 90
    assert len(rows) == 2
    assert rows[0]["product"] == "ALPHA-1"
    assert rows[0]["customer_name"] == "Acme"
    assert rows[0]["transaction_date"] == "2026-04-02"
    assert rows[0]["original_unit"] == "KG"
    assert "Q1" in rows[0]["period"]
    assert rows[1]["product"] == "BETA-9"
    assert "Q3" in rows[1]["period"]
    assert float(sum(row["sales_quantity"] for row in rows)) == 35
