"""Email body tables become the same matrix rows as an Excel import."""

from app.erp_parser.documents.email_body import extract_email_body_grid
from app.erp_parser.email_body_matrix import extract_email_body_matrix_rows
from app.erp_parser.parser_service import ERPParserService
from app.utils.email_subject_parser import parse_email_subject

_BODY = """
| Badamikar                             | Apr | May | June |
| ------------------------------------- | --: | --: | ---: |
| **APCOTEX TX 400**                    |     |     |      |
| M/S VIJAY ANAND FABRIC                | 100 |   0 |  100 |
| M/S MARUTI COTTEX LTD                 | 100 | 100 |   50 |
| M/S RADHA MADHAV CORPORATION          | 100 |   0 |  100 |
| M/S NAVSHAKTI TEXTILES PROC. PVT. LTD |  50 | 100 |    0 |
| M/S. VR TEX PROCESSOR PRIVATE LTD     | 150 |  50 |   50 |

APCOTEX SR 558
M/S VIJAY ANAND FABRIC    10 20 30
"""

_HTML = """
<html><body>
<table>
<tr><td>Badamikar</td><td>Apr</td><td>May</td><td>June</td></tr>
<tr><td><strong>APCOTEX TX 400</strong></td><td></td><td></td><td></td></tr>
<tr><td>M/S VIJAY ANAND FABRIC</td><td>100</td><td>0</td><td>100</td></tr>
<tr><td>M/S MARUTI COTTEX LTD</td><td>100</td><td>100</td><td>50</td></tr>
</table>
<p>APCOTEX SR 558</p>
<table>
<tr><td>Badamikar</td><td>Apr</td><td>May</td><td>June</td></tr>
<tr><td>M/S RADHA MADHAV CORPORATION</td><td>5</td><td>0</td><td>7</td></tr>
</table>
</body></html>
"""


_V5_BODY = """
| Badamikar                | Apr | May | Jun |
| ------------------------ | --: | --: | --: |
| **APCOTEX TX 400**       |     |     |     |
| Vijay Anand Fabric       | 100 |   0 | 100 |
| Maruti Cottex Ltd        | 100 | 100 |  50 |
| Radha Madhav Corporation | 100 |   0 | 100 |
| Navshakti Textiles       |  50 | 100 |   0 |
| VR Tex Processor Pvt Ltd | 150 |  50 |  50 |
"""


def test_subject_region_segment_period_unit():
    parsed = parse_email_subject("Badamikar & Co.|WEST|RUBBER|Q1 FY 2026-27|KG")
    assert parsed["distributor"] == "Badamikar & Co."
    assert parsed["region"] == "West"
    assert parsed["segment"] == "Rubber"
    assert parsed["quarter"] == "Q1"
    assert parsed["financial_year"] == "FY 2026-27"
    assert parsed["unit"] == "KG"
    assert "Q1" in (parsed["period"] or "")


def test_v5_body_matrix_fifteen_rows():
    parsed = parse_email_subject("Badamikar & Co.|WEST|RUBBER|Q1 FY 2026-27|KG")
    grid = extract_email_body_grid(text=_V5_BODY)
    assert grid is not None
    from app.erp_parser.documents.materialize import materialize_grid

    path = materialize_grid(grid, source_name="Email Body.xlsx")
    try:
        result = ERPParserService().parse_workbook(
            path,
            fiscal_year_start=2026,
            reporting_quarter=parsed["period"],
            distributor_label=parsed["distributor"],
        )
    finally:
        path.unlink(missing_ok=True)
    breakdown = result.confidence_breakdown or {}
    assert breakdown.get("parser_name") == "email_body_matrix"
    assert breakdown.get("layout_name") == "email_matrix"
    assert breakdown.get("document_type") == "Email Body"
    assert result.overall_confidence == 98
    assert breakdown.get("llm_used") is False
    assert len(result.rows) == 15
    customers = {row["customer_name"] for row in result.rows}
    assert customers == {
        "Vijay Anand Fabric",
        "Maruti Cottex Ltd",
        "Radha Madhav Corporation",
        "Navshakti Textiles",
        "VR Tex Processor Pvt Ltd",
    }
    vijay = [row for row in result.rows if row["customer_name"] == "Vijay Anand Fabric"]
    by_month = {row["source_month"]: row["sales_quantity"] for row in vijay}
    assert by_month == {"April 2026": 100.0, "May 2026": 0.0, "June 2026": 100.0}
    assert all(row["product"] == "APCOTEX TX 400" for row in result.rows)
    assert all(row["original_unit"] == "KG" for row in result.rows)
    assert all("Q1" in str(row["period"]) for row in result.rows)


def test_standard_four_part_subject_unchanged():
    parsed = parse_email_subject("Chaudhury | South | Rubber | Q2 FY 2025-26")
    assert parsed["location"] == "South"
    assert parsed["segment"] == "Rubber"
    assert parsed["quarter"] == "Q2"
    assert parsed["unit"] == "MT"


def test_plain_text_keeps_zero_and_switches_product():
    grid = extract_email_body_grid(text=_BODY)
    assert grid is not None
    assert grid.sheets[0].name == "Email Body"
    extracted = extract_email_body_matrix_rows(
        grid.sheets[0].rows,
        sheet_name="Email Body",
        fiscal_year_start=2026,
    )
    assert extracted is not None
    rows = extracted["rows"]
    vijay = [row for row in rows if row["customer_name"] == "Vijay Anand Fabric" and row["product"] == "APCOTEX TX 400"]
    by_month = {row["source_month"]: row["sales_quantity"] for row in vijay}
    assert by_month["April 2026"] == 100
    assert by_month["May 2026"] == 0
    assert by_month["June 2026"] == 100
    second = [row for row in rows if row["product"] == "APCOTEX SR 558"]
    assert len(second) == 3
    assert extracted["products_detected"] == 2
    assert extracted["layout"] == "email_matrix"
    assert all(row["original_unit"] == "KG" for row in rows)


def test_html_table_and_orchestrator_confidence():
    grid = extract_email_body_grid(html=_HTML)
    assert grid is not None
    from app.erp_parser.documents.materialize import materialize_grid

    path = materialize_grid(grid, source_name="Email Body.xlsx")
    try:
        result = ERPParserService().parse_workbook(path, fiscal_year_start=2026, reporting_quarter="FY 2026-27 • Q1")
    finally:
        path.unlink(missing_ok=True)
    breakdown = result.confidence_breakdown or {}
    assert breakdown.get("parser_name") == "email_body_matrix"
    assert breakdown.get("parser_label") == "Email Body Matrix"
    assert breakdown.get("layout_name") == "email_matrix"
    assert breakdown.get("document_type") == "Email Body"
    assert result.overall_confidence == 98
    assert breakdown.get("llm_used") is False
    may_zero = [
        row
        for row in result.rows
        if row["customer_name"] == "Vijay Anand Fabric" and row["source_month"] == "May 2026"
    ]
    assert may_zero and may_zero[0]["sales_quantity"] == 0
    assert any(row["product"] == "APCOTEX SR 558" for row in result.rows)
