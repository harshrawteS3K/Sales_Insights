"""LLM fallback — semantic column mapping only (never extracts rows)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

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
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class LLMHeaderResolverError(Exception):
    """Raised when the OpenAI header resolver cannot produce a mapping."""


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

    return {
        "customer_column": _col("customer_column"),
        "product_column": _col("product_column"),
        "quantity_column": _col("quantity_column"),
        "confidence": int(round(confidence)),
    }


class LLMHeaderResolver:
    """OpenAI-backed semantic column mapper (headers + sample cells only)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        # Prefer admin Settings overrides (model / enable / key from env)
        try:
            from app.database.session import SessionLocal
            from app.services.llm_settings_service import resolve_runtime_llm

            _db = SessionLocal()
            try:
                rt = resolve_runtime_llm(_db)
            finally:
                _db.close()
        except Exception:  # noqa: BLE001
            rt = {
                "enabled": bool((settings.openai_api_key or "").strip()),
                "api_key": (settings.openai_api_key or "").strip(),
                "model": settings.openai_model or "gpt-5.4-mini",
                "timeout": float(settings.openai_timeout_seconds or 30),
            }

        self._llm_enabled = bool(rt.get("enabled"))
        self.api_key = (api_key if api_key is not None else rt.get("api_key")) or ""
        self.model = (model if model is not None else rt.get("model")) or "gpt-4o-mini"
        self.timeout = float(
            timeout if timeout is not None else rt.get("timeout") or settings.openai_timeout_seconds or 30
        )

    def resolve_headers(
        self,
        headers: list[str],
        sample_rows: list[list[str]],
    ) -> Dict[str, Any]:
        """
        Identify Customer / Product / Sales Quantity columns.

        Returns only:
        ``{customer_column, product_column, quantity_column, confidence}``
        """
        clean_headers = sanitize_headers(headers)
        clean_rows = sanitize_sample_rows(sample_rows, header_count=len(clean_headers))
        if not clean_headers:
            raise LLMHeaderResolverError("No headers provided")

        if not self._llm_enabled:
            raise LLMHeaderResolverError("LLM is disabled in Admin Settings")

        if not self.api_key:
            raise LLMHeaderResolverError("OPENAI_API_KEY is not configured")

        user_payload = {"headers": clean_headers, "sample_rows": clean_rows}
        est = estimate_payload_tokens(clean_headers, clean_rows)
        if est > 500:
            logger.warning(
                "LLM Header Resolver token estimate high | estimate={} | truncating samples",
                est,
            )
            clean_rows = clean_rows[:2]
            user_payload = {"headers": clean_headers, "sample_rows": clean_rows}

        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=True),
                },
            ],
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    OPENAI_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise LLMHeaderResolverError(f"OpenAI timeout: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMHeaderResolverError(
                f"OpenAI HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMHeaderResolverError(f"OpenAI network error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMHeaderResolverError(f"OpenAI request failed: {exc}") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMHeaderResolverError("Unexpected OpenAI response shape") from exc

        usage = payload.get("usage") if isinstance(payload, dict) else None
        try:
            from app.database.session import SessionLocal
            from app.services.llm_settings_service import LlmSettingsService

            _db = SessionLocal()
            try:
                LlmSettingsService(_db).record_usage(
                    purpose="header_mapping",
                    usage=usage if isinstance(usage, dict) else {},
                    model=self.model,
                    provider="openai",
                )
                _db.commit()
            finally:
                _db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist LLM usage | purpose=header_mapping | err={}", exc)

        return parse_llm_mapping_json(content)
