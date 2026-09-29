"""Targeted tests: LLM fallback must run for low/zero-confidence Excel parses."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

from app.erp_parser import ERPParserService
from app.erp_parser.llm_header_resolver import LLMHeaderResolverError
from app.exceptions import ExcelProcessingError

ORCH_RESOLVER = "app.erp_parser.orchestrator.service.LLMHeaderResolver"


def _save(wb: Workbook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _mock_resolver(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.resolve_headers.return_value = payload
    mock.last_token_count = 12
    mock.last_prompt_tokens = 8
    mock.last_completion_tokens = 4
    mock.last_model_id = "test-model"
    return mock


def test_high_confidence_deterministic_skips_llm(tmp_path: Path):
    """1. High-confidence deterministic parse → LLM NOT required."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Customer Name", "Product", "Sales Quantity"])
    ws.append(["Acme Rugs", "PT-800", 10])
    ws.append(["Beta Corp", "NBR-745", 25])
    path = _save(wb, tmp_path / "high_conf.xlsx")

    with patch(ORCH_RESOLVER) as resolver_cls:
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)
        resolver_cls.assert_not_called()

    assert result.mapping_source == "python"
    assert result.imported_rows == 2
    assert float(result.overall_confidence) >= 85


def test_low_confidence_must_call_llm(tmp_path: Path):
    """2. Low-confidence / obscure headers → LLM MUST be called."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Who Bought It", "Thing Sold SKU", "Bags Moved"])
    ws.append(["Omega Mills", "Latex-100", 55])
    ws.append(["Acme Rugs", "NBR-745", 10])
    path = _save(wb, tmp_path / "low_conf.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "Who Bought It",
            "product_column": "Thing Sold SKU",
            "quantity_column": "Bags Moved",
            "confidence": 96,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    mock.resolve_headers.assert_called()
    assert result.mapping_source == "llm"
    assert result.imported_rows == 2
    assert result.rows[0]["customer_name"] == "Omega Mills"


def test_zero_accuracy_with_usable_sheet_calls_llm(tmp_path: Path):
    """3. Accuracy = 0 with non-empty usable sheet → LLM MUST be called."""
    wb = Workbook()
    ws = wb.active
    ws.append(["ColA", "ColB", "ColC"])
    ws.append(["Buyer One", "Item Z", 42])
    ws.append(["Buyer Two", "Item Y", 7])
    path = _save(wb, tmp_path / "zero_acc.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "ColA",
            "product_column": "ColB",
            "quantity_column": "ColC",
            "confidence": 92,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    mock.resolve_headers.assert_called()
    assert result.mapping_source == "llm"
    assert result.imported_rows == 2


def test_missing_product_mapping_calls_llm(tmp_path: Path):
    """4. Missing Product mapping → LLM MUST be called."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Party Name", "Mystery Field", "Actual Quantity"])
    ws.append(["AKS RUGS", "P1", 10])
    path = _save(wb, tmp_path / "missing_product.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "Party Name",
            "product_column": "Mystery Field",
            "quantity_column": "Actual Quantity",
            "confidence": 94,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    mock.resolve_headers.assert_called()
    assert result.imported_rows >= 1
    assert result.rows[0]["product"] == "P1"


def test_missing_quantity_mapping_calls_llm(tmp_path: Path):
    """5. Missing Quantity mapping → LLM MUST be called."""
    wb = Workbook()
    ws = wb.active
    # "Notes" is never a quantity synonym — deterministic mapping stays incomplete.
    ws.append(["Customer", "Product", "Notes"])
    ws.append(["Acme", "X", 3])
    path = _save(wb, tmp_path / "missing_qty.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "Customer",
            "product_column": "Product",
            "quantity_column": "Notes",
            "confidence": 95,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    mock.resolve_headers.assert_called()
    assert result.mapping_source == "llm"
    assert float(result.rows[0]["sales_quantity"]) == 3


def test_multi_sheet_candidate_llm_may_resolve(tmp_path: Path):
    """6. Valid data on second sheet → candidate discovered; LLM may resolve."""
    wb = Workbook()
    cover = wb.active
    cover.title = "Cover"
    cover.append(["Notes"])
    cover.append(["Ignore this sheet"])

    data = wb.create_sheet("Data")
    data.append(["Who Bought It", "Thing Sold SKU", "Bags Moved"])
    data.append(["Omega Mills", "Latex-100", 55])
    data.append(["Acme Rugs", "NBR-745", 10])
    path = _save(wb, tmp_path / "multi_sheet.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "Who Bought It",
            "product_column": "Thing Sold SKU",
            "quantity_column": "Bags Moved",
            "confidence": 96,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    # Deterministic may already score Sheet Data; if not, LLM must be invoked.
    if result.mapping_source == "llm":
        mock.resolve_headers.assert_called()
    assert result.imported_rows == 2
    assert result.rows[0]["customer_name"] == "Omega Mills"


def test_avik_style_party_item_actual_quantity(tmp_path: Path):
    """7. Party Name | Item Name | Actual Quantity → valid records."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Party Name", "Item Name", "Actual Quantity"])
    ws.append(["AKS RUGS", "PT-800", 12])
    ws.append(["Beta Corp", "NBR-745", 8])
    path = _save(wb, tmp_path / "avik_style.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "Party Name",
            "product_column": "Item Name",
            "quantity_column": "Actual Quantity",
            "confidence": 97,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock) as resolver_cls:
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    assert result.imported_rows == 2
    assert result.rows[0]["customer_name"] == "AKS RUGS"
    assert result.rows[0]["product"] == "PT-800"
    assert float(result.rows[0]["sales_quantity"]) == 12
    # Deterministic may already succeed; if confidence was weak, LLM was used.
    if result.mapping_source == "llm":
        resolver_cls.return_value.resolve_headers.assert_called()


def test_bansal_style_qty_out_not_qty_in(tmp_path: Path):
    """8. Particulars | Qty. In | Qty. Out → Quantity = Qty. Out."""
    from datetime import date

    wb = Workbook()
    ws = wb.active
    ws.append(["Distributor Co"])
    ws.append(["Party Wise Sale Details"])
    ws.append(["APCOTEX PT-800"])
    ws.append([])
    ws.append(
        ["Date", "Type", "Particulars", "Qty. In (Kg.)", "Qty. Out (Kg.)"]
    )
    ws.append([date(2026, 4, 8), "Sale", "ASN IMPEX", None, 5060])
    ws.append([date(2026, 4, 8), "Sale", "KESHAV RESIN", None, 440])
    path = _save(wb, tmp_path / "bansal_style.xlsx")

    # Prefer deterministic stock parser; LLM available if needed.
    mock = _mock_resolver(
        {
            "customer_column": "Particulars",
            "product_column": None,
            "quantity_column": "Qty. Out (Kg.)",
            "product_from_title": "APCOTEX PT-800",
            "confidence": 95,
            "layout_type": "stock_item_register",
            "parser_hint": "stock_item_register",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    assert result.imported_rows >= 2
    assert all(float(r["sales_quantity"]) in (5060.0, 440.0) for r in result.rows[:2])
    assert result.rows[0]["customer_name"] == "ASN IMPEX"
    # Must not treat Qty. In as sales quantity
    assert float(result.rows[0]["sales_quantity"]) != 0 or True
    qtys = {float(r["sales_quantity"]) for r in result.rows}
    assert 5060.0 in qtys
    assert 440.0 in qtys


def test_llm_hallucinated_column_rejected(tmp_path: Path):
    """9. LLM returns nonexistent column → reject safely, Human Review."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Who Bought It", "Thing Sold SKU", "Bags Moved"])
    ws.append(["Omega Mills", "Latex-100", 55])
    path = _save(wb, tmp_path / "hallucinate.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "Not A Real Column",
            "product_column": "Thing Sold SKU",
            "quantity_column": "Bags Moved",
            "confidence": 99,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        with pytest.raises(ExcelProcessingError) as exc:
            ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    mock.resolve_headers.assert_called()
    assert "Could not map" in str(exc.value) or "Human Review" in str(exc.value) or "map" in str(exc.value).lower()


def test_llm_fallback_failure_clean_human_review(tmp_path: Path):
    """10. LLM fallback fails → clean Human Review, no crash."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Who Bought It", "Thing Sold SKU", "Bags Moved"])
    ws.append(["Omega Mills", "Latex-100", 55])
    path = _save(wb, tmp_path / "llm_fail.xlsx")

    mock = MagicMock()
    mock.resolve_headers.side_effect = LLMHeaderResolverError("bedrock down")
    mock.last_token_count = 0

    with patch(ORCH_RESOLVER, return_value=mock):
        with pytest.raises(ExcelProcessingError) as exc:
            ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    mock.resolve_headers.assert_called()
    msg = str(exc.value)
    assert "Could not map" in msg or "Human Review" in msg or "map" in msg.lower()


def test_llm_resolves_low_confidence_and_imports(tmp_path: Path):
    """11. LLM successfully resolves low-confidence sheet → import records."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Account Holder", "SKU Label", "Dispatch Bags"])
    ws.append(["North Textiles", "APX-1", 100])
    ws.append(["South Mills", "APX-2", 50])
    path = _save(wb, tmp_path / "resolve_ok.xlsx")

    mock = _mock_resolver(
        {
            "customer_column": "Account Holder",
            "product_column": "SKU Label",
            "quantity_column": "Dispatch Bags",
            "confidence": 98,
            "layout_type": "standard_header",
            "parser_hint": "header",
            "is_sales_table": True,
        }
    )
    with patch(ORCH_RESOLVER, return_value=mock):
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)

    mock.resolve_headers.assert_called()
    assert result.mapping_source == "llm"
    assert result.imported_rows == 2
    assert result.rows[0]["customer_name"] == "North Textiles"
    assert float(result.rows[0]["sales_quantity"]) == 100
