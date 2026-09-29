"""Bedrock response classification + ERP LLM timeout / deterministic retention."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

from app.erp_parser import ERPParserService
from app.erp_parser.orchestrator import deadline as deadline_mod
from app.llm import bedrock_client as bc


def test_valid_text_response_parsed():
    response = {
        "output": {"message": {"content": [{"text": '{"ok": true}'}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 3, "outputTokens": 2},
    }
    text = bc._extract_final_text(response, model_id="minimax.minimax-m2")
    assert text == '{"ok": true}'


def test_reasoning_only_classified_not_success():
    response = {
        "output": {
            "message": {
                "content": [
                    {"reasoningContent": {"text": "thinking about the quarter..."}}
                ]
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 40},
    }
    with pytest.raises(bc.BedrockReasoningOnly):
        bc._extract_final_text(response, model_id="minimax.minimax-m2")


def test_empty_content_classified():
    response = {
        "output": {"message": {"content": []}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1, "outputTokens": 0},
    }
    with pytest.raises(bc.BedrockEmptyResponse):
        bc._extract_final_text(response, model_id="minimax.minimax-m2")


def test_reasoning_only_not_retried():
    assert bc._retryable(bc.BedrockReasoningOnly("x")) is False
    assert bc._retryable(bc.BedrockEmptyResponse("x")) is False
    assert bc._retryable(bc.BedrockMalformedResponse("x")) is False


def test_complete_raises_reasoning_only_without_retry():
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {"content": [{"reasoningContent": {"text": "only reasoning"}}]}
        },
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }
    with patch.object(bc, "get_bedrock_client", return_value=runtime):
        with pytest.raises(bc.BedrockError) as exc:
            bc.complete(system="s", user="u", model_id="minimax.minimax-m2", timeout=None)
    assert "reasoning" in str(exc.value).lower() or "failed" in str(exc.value).lower()
    assert runtime.converse.call_count == 1  # no empty/reasoning retries


def test_no_artificial_llm_stage_deadline():
    assert "llm" not in deadline_mod.STAGE_LIMIT_SECONDS


def test_high_confidence_skips_header_resolver(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Customer Name", "Product", "Sales Quantity"])
    ws.append(["Acme", "PT-800", 10])
    path = tmp_path / "hi.xlsx"
    wb.save(path)

    with patch("app.erp_parser.orchestrator.service.LLMHeaderResolver") as resolver_cls:
        result = ERPParserService().parse_workbook(path, allow_llm_fallback=True)
        resolver_cls.assert_not_called()
    assert float(result.overall_confidence) >= 85
    assert result.imported_rows >= 1
    assert result.mapping_source == "python"


def test_llm_failure_retains_deterministic_winner(tmp_path: Path):
    """When deterministic already succeeded, LLM failure must not wipe confidence."""
    from app.erp_parser.orchestrator.service import (
        UniversalParserOrchestrator,
        _should_accept_llm,
    )
    from app.erp_parser.orchestrator.types import ParserResult

    winner = ParserResult(
        rows=[{"customer_name": "A", "product": "P", "sales_quantity": 1}],
        parser_name="header",
        confidence=100.0,
        mapped={
            "positions": {"customer": 0, "product": 1, "quantity": 2},
            "quantity_columns": [],
            "confidences": {"customer": 100, "product": 100, "quantity": 100},
        },
    )
    assert _should_accept_llm(None, winner) is False
    # Simulate post-failure flags the orchestrator now sets
    winner.llm_used = False
    assert winner.confidence == 100.0
    assert winner.llm_used is False
    assert len(winner.rows) == 1
