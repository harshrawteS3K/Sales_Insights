"""LLM fallback — semantic column mapping only (never extracts rows)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.bedrock_client import BedrockError, complete
from app.llm.model_registry import default_model_id, resolve_model_id

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an ERP semantic column mapping engine.

Your ONLY task is to identify which spreadsheet columns correspond to:

1. Customer Name
2. Product
3. Sales Quantity

You will receive:

* a list of column headers
* 2–3 sample rows

Rules:

* Do not extract rows.
* Do not infer distributor.
* Do not infer quarter.
* Do not summarize.
* Return valid JSON only.
* Confidence should be 0–100.
* If uncertain, return null for that field.

Output JSON:

{
"customer_column":"",
"product_column":"",
"quantity_column":"",
"confidence":0
}"""

MAX_HEADERS = 15
MAX_SAMPLE_ROWS = 3


class LLMHeaderResolverError(Exception):
    """Raised when the structure analyzer cannot produce a mapping."""


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    # Keep payload tiny — truncate long cells
    return text[:80]


def sanitize_headers(headers: List[Any], *, limit: int = MAX_HEADERS) -> List[str]:
    """Plain-text headers only; cap count for token safety."""
    out: List[str] = []
    for h in headers:
        text = _cell_text(h)
        if not text:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def sanitize_sample_rows(
    sample_rows: List[List[Any]],
    *,
    header_count: int,
    limit: int = MAX_SAMPLE_ROWS,
) -> List[List[str]]:
    """Plain-text sample values only; max 3 rows × header_count cells."""
    rows: List[List[str]] = []
    width = max(0, int(header_count))
    for raw in sample_rows:
        if len(rows) >= limit:
            break
        cells = list(raw or [])
        row = [_cell_text(cells[i] if i < len(cells) else "") for i in range(width)]
        if any(row):
            rows.append(row)
    return rows


def estimate_payload_tokens(headers: List[str], sample_rows: List[List[str]]) -> int:
    """Rough token estimate (~4 chars/token) for the user JSON payload."""
    payload = json.dumps({"headers": headers, "sample_rows": sample_rows}, ensure_ascii=True)
    return max(1, len(payload) // 4) + max(1, len(SYSTEM_PROMPT) // 4)


def parse_llm_mapping_json(raw: str) -> Dict[str, Any]:
    """Parse and normalize LLM JSON into the required 4-field shape."""
    text = (raw or "").strip()
    if not text:
        raise LLMHeaderResolverError("Empty LLM response")

    # Strip optional markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMHeaderResolverError(f"Invalid JSON from LLM: {exc}") from exc

    if not isinstance(data, dict):
        raise LLMHeaderResolverError("LLM response is not a JSON object")

    def _col(key: str) -> Optional[str]:
        val = data.get(key)
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.lower() in {"null", "none", "n/a"}:
            return None
        return s

    conf_raw = data.get("confidence", 0)
    try:
        confidence = float(conf_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(100.0, confidence))

    ignore = data.get("ignore_columns") or []
    if not isinstance(ignore, list):
        ignore = [str(ignore)]
    return {
        "customer_column": _col("customer_column"),
        "product_column": _col("product_column"),
        "quantity_column": _col("quantity_column"),
        "parser_hint": _col("parser_hint") or "",
        "layout_type": str(data.get("layout_type") or "").strip(),
        "product_header_row": data.get("product_header_row"),
        "month_header_row": data.get("month_header_row"),
        "ignore_columns": [str(item) for item in ignore if str(item).strip()],
        "grouping": str(data.get("grouping") or "").strip(),
        "confidence": int(round(confidence)),
    }


class LLMHeaderResolver:
    """Bedrock-backed structure analyzer. It returns layout JSON. Python extracts rows."""

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
        self.last_token_count = 0
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0

    def _runtime_settings(self) -> Dict[str, Any]:
        """Current admin selection. Read on each call so a Settings change needs no restart."""
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

    def resolve_headers(
        self,
        headers: list[str],
        sample_rows: list[list[str]],
        *,
        sample_limit: int = MAX_SAMPLE_ROWS,
        system_prompt: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Identify Customer / Product / Sales Quantity columns.

        Returns column names and confidence. Row extraction stays in Python.
        """
        prompt = system_prompt or SYSTEM_PROMPT
        clean_headers = sanitize_headers(headers)
        clean_rows = sanitize_sample_rows(
            sample_rows,
            header_count=len(clean_headers),
            limit=sample_limit,
        )
        if not clean_headers:
            raise LLMHeaderResolverError("No headers provided")

        if not self._llm_enabled:
            raise LLMHeaderResolverError("LLM is disabled in Admin Settings")

        reason = str((extra or {}).get("reason") or "")
        user_payload = {"headers": clean_headers, "sample_rows": clean_rows}
        if extra:
            user_payload.update({key: value for key, value in extra.items() if key != "reason"})
        est = estimate_payload_tokens(clean_headers, clean_rows)
        if est > 500:
            logger.warning(
                "LLM Header Resolver token estimate high | estimate={} | truncating samples",
                est,
            )
            clean_rows = clean_rows[:2]
            user_payload["sample_rows"] = clean_rows

        try:
            result = complete(
                system=prompt,
                user=json.dumps(user_payload, ensure_ascii=True),
                model_id=self._model_for_request(),
                timeout=self.timeout,
                reason=reason,
            )
        except BedrockError as exc:
            raise LLMHeaderResolverError(str(exc)) from exc

        self.last_model_id = result.model_id
        usage = result.usage()
        self.last_prompt_tokens = int(usage["prompt_tokens"])
        self.last_completion_tokens = int(usage["completion_tokens"])
        self.last_token_count = int(usage["total_tokens"])
        try:
            from app.database.session import SessionLocal
            from app.services.llm_settings_service import LlmSettingsService

            _db = SessionLocal()
            try:
                LlmSettingsService(_db).record_usage(
                    purpose="header_mapping",
                    usage=usage,
                    model=result.model_id,
                    provider="bedrock",
                )
                _db.commit()
            finally:
                _db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist LLM usage | purpose=header_mapping | err={}", exc)

        return parse_llm_mapping_json(result.text)
