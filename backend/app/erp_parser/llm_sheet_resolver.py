"""LLM fallback — pick the best sales worksheet when deterministic scoring is weak."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from app.core.config import get_settings
from app.core.logging import get_logger
from app.erp_parser.workbook_detector import list_candidate_sheets, read_sheet_matrix
from app.llm.bedrock_client import BedrockError, complete
from app.llm.model_registry import default_model_id, resolve_model_id

logger = get_logger(__name__)

SYSTEM_PROMPT = """You pick which Excel worksheet contains distributor sales data.

You receive sheet names and a tiny preview of each sheet (first few non-empty cells).

Rules:
* Return valid JSON only.
* Choose exactly one sheet_name from the provided list.
* Prefer sheets with customer names and product/quantity values.
* Ignore cover, index, summary, pivot, chart-only sheets when a data sheet exists.

Output JSON:
{"sheet_name":"","confidence":0,"reason":""}
"""


class LLMSheetResolverError(Exception):
    """Raised when the OpenAI sheet resolver cannot pick a sheet."""


def _preview_cells(matrix: Sequence[Sequence[Any]], *, max_rows: int = 4, max_cols: int = 8) -> List[List[str]]:
    out: List[List[str]] = []
    for row in matrix[:max_rows]:
        cells = []
        for cell in list(row)[:max_cols]:
            text = "" if cell is None else str(cell).strip()[:60]
            cells.append(text)
        if any(cells):
            out.append(cells)
    return out


def parse_llm_sheet_json(raw: str, candidates: Sequence[str]) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise LLMSheetResolverError("Empty LLM response")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMSheetResolverError(f"Invalid JSON from LLM: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMSheetResolverError("LLM response is not a JSON object")

    name = str(data.get("sheet_name") or "").strip()
    if not name:
        raise LLMSheetResolverError("LLM did not return sheet_name")

    by_fold = {c.casefold(): c for c in candidates}
    if name in candidates:
        resolved = name
    elif name.casefold() in by_fold:
        resolved = by_fold[name.casefold()]
    else:
        # soft contains match
        resolved = next(
            (c for c in candidates if name.casefold() in c.casefold() or c.casefold() in name.casefold()),
            None,
        )
        if not resolved:
            raise LLMSheetResolverError(f"LLM sheet '{name}' not in candidates")

    try:
        confidence = float(data.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "sheet_name": resolved,
        "confidence": max(0.0, min(100.0, confidence)),
        "reason": str(data.get("reason") or "")[:200],
    }


class LLMSheetResolver:
    """Bedrock-backed worksheet picker."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        del api_key
        self._explicit_model = resolve_model_id(model) if model is not None else None
        settings = get_settings()
        runtime = self._runtime_settings()
        self._llm_enabled = bool(runtime.get("enabled", True))
        self.timeout = float(
            timeout if timeout is not None else runtime.get("timeout") or settings.bedrock_timeout or 30
        )

    def _runtime_settings(self) -> Dict[str, Any]:
        settings = get_settings()
        try:
            from app.database.session import SessionLocal
            from app.services.llm_settings_service import resolve_runtime_llm

            _db = SessionLocal()
            try:
                return resolve_runtime_llm(_db)
            finally:
                _db.close()
        except Exception:  # noqa: BLE001
            return {
                "enabled": True,
                "model": default_model_id(),
                "timeout": float(settings.bedrock_timeout or 30),
            }

    def _model_for_request(self) -> str:
        if self._explicit_model:
            return self._explicit_model
        return resolve_model_id(self._runtime_settings().get("model"))

    def pick_sheet(
        self,
        path: Union[str, Path],
        *,
        candidates: Optional[Sequence[str]] = None,
    ) -> Tuple[str, float]:
        """Return ``(sheet_name, confidence)``."""
        if not self._llm_enabled:
            raise LLMSheetResolverError("LLM is disabled in Admin Settings")

        names = list(candidates or list_candidate_sheets(path))
        if not names:
            raise LLMSheetResolverError("No candidate sheets")
        if len(names) == 1:
            return names[0], 90.0

        previews: List[Dict[str, Any]] = []
        for name in names[:20]:
            try:
                matrix = read_sheet_matrix(path, name, max_rows=8, max_cols=10)
                previews.append({"sheet_name": name, "preview": _preview_cells(matrix)})
            except Exception as exc:  # noqa: BLE001
                previews.append({"sheet_name": name, "preview": [], "error": str(exc)[:80]})

        try:
            result = complete(
                system=SYSTEM_PROMPT,
                user=json.dumps(
                    {"sheets": previews, "candidates": names[:20]},
                    ensure_ascii=True,
                ),
                model_id=self._model_for_request(),
                timeout=self.timeout,
                reason="Sheet selection",
            )
        except BedrockError as exc:
            raise LLMSheetResolverError(str(exc)) from exc
        usage = result.usage()
        try:
            from app.database.session import SessionLocal
            from app.services.llm_settings_service import LlmSettingsService

            _db = SessionLocal()
            try:
                LlmSettingsService(_db).record_usage(
                    purpose="sheet_detect",
                    usage=usage,
                    model=result.model_id,
                    provider="bedrock",
                )
                _db.commit()
            finally:
                _db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist LLM usage | purpose=sheet_detect | err={}", exc)

        parsed = parse_llm_sheet_json(result.text, names)
        logger.info(
            "LLM sheet pick | sheet={} | confidence={} | reason={}",
            parsed["sheet_name"],
            parsed["confidence"],
            parsed.get("reason"),
        )
        return parsed["sheet_name"], float(parsed["confidence"])
