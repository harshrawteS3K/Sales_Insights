"""Amazon Bedrock runtime client. Credentials come from the IAM role chain."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.model_registry import resolve_model_id

logger = get_logger(__name__)

_MAX_RETRIES = 2
_RETRYABLE = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ModelTimeoutException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
}

_client: Any = None
_client_key: Optional[tuple[str, float]] = None


class BedrockError(Exception):
    """Raised when Bedrock does not return JSON text."""


@dataclass
class BedrockCompletion:
    text: str
    model_id: str
    region: str
    input_tokens: int
    output_tokens: int
    latency_ms: int

    def usage(self) -> dict[str, int]:
        total = self.input_tokens + self.output_tokens
        return {
            "prompt_tokens": self.input_tokens,
            "completion_tokens": self.output_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": total,
        }


def get_bedrock_client(region: str, timeout: float) -> Any:
    """One runtime client per region and timeout. No access keys are passed."""
    global _client, _client_key
    key = (region, float(timeout))
    if _client is not None and _client_key == key:
        return _client
    _client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(
            connect_timeout=min(10.0, float(timeout)),
            read_timeout=float(timeout),
            retries={"max_attempts": 1},
        ),
    )
    _client_key = key
    return _client


def complete(
    *,
    system: str,
    user: str,
    model_id: Optional[str] = None,
    timeout: Optional[float] = None,
    reason: str = "",
) -> BedrockCompletion:
    """Send one JSON-only chat completion. The prompt text is the caller's."""
    settings = get_settings()
    region = (settings.aws_region or "ap-south-1").strip() or "ap-south-1"
    resolved_model = resolve_model_id(model_id or settings.default_model)
    limit = float(timeout if timeout is not None else settings.bedrock_timeout or 30)
    client = get_bedrock_client(region, limit)
    started = time.perf_counter()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.converse(
                modelId=resolved_model,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"temperature": 0.0, "maxTokens": 800},
            )
            text = _message_text(response)
            if not text.strip():
                raise BedrockError("Bedrock returned an empty response")
            usage = response.get("usage") if isinstance(response, dict) else {}
            if not isinstance(usage, dict):
                usage = {}
            result = BedrockCompletion(
                text=text,
                model_id=resolved_model,
                region=region,
                input_tokens=int(usage.get("inputTokens") or 0),
                output_tokens=int(usage.get("outputTokens") or 0),
                latency_ms=int(round((time.perf_counter() - started) * 1000)),
            )
            logger.info(
                "LLM Provider: AWS Bedrock\n"
                "Model: {}\n"
                "Region: {}\n"
                "Latency: {} ms\n"
                "Input Tokens: {}\n"
                "Output Tokens: {}\n"
                "Reason: {}",
                result.model_id,
                result.region,
                result.latency_ms,
                result.input_tokens,
                result.output_tokens,
                reason or "",
            )
            return result
        except (ClientError, BotoCoreError, ReadTimeoutError, BedrockError) as exc:
            last_error = exc
            if attempt >= _MAX_RETRIES or not _retryable(exc):
                break
            logger.warning(
                "Bedrock retry | attempt={} | model={} | err={}",
                attempt + 1,
                resolved_model,
                exc,
            )
    raise BedrockError(f"Bedrock request failed: {last_error}") from last_error


def _message_text(response: Any) -> str:
    try:
        content = response["output"]["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise BedrockError("Unexpected Bedrock response shape") from exc
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, (ReadTimeoutError, BedrockError)):
        return not isinstance(exc, BedrockError) or "empty response" in str(exc).lower()
    if isinstance(exc, BotoCoreError) and not isinstance(exc, ClientError):
        return True
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code") or "")
        return code in _RETRYABLE
    return False
