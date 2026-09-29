"""Amazon Bedrock runtime client. Credentials come from the IAM role chain."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ReadTimeoutError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.model_registry import display_name_for, resolve_model_id

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

# Network-level ceiling only when the caller does not pass a timeout.
# Not an ERP business deadline — prevents hung sockets.
_DEFAULT_NETWORK_TIMEOUT = 900.0

_client: Any = None
_client_key: Optional[tuple[str, float]] = None


class BedrockError(Exception):
    """Raised when Bedrock does not return usable JSON text."""


class BedrockEmptyResponse(BedrockError):
    """Converse returned no content blocks / no usable payload."""


class BedrockReasoningOnly(BedrockError):
    """Model returned reasoningContent without a final text answer."""


class BedrockMalformedResponse(BedrockError):
    """Response shape is unexpected or has content without extractable text."""


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
    """Send one JSON-only chat completion. The prompt text is the caller's.

    ``timeout=None`` means no ERP artificial deadline — only a network-level
    read ceiling (settings.bedrock_timeout, or 900s) so sockets cannot hang forever.
    """
    settings = get_settings()
    region = (
        (settings.bedrock_region or settings.aws_region or "ap-south-1").strip()
        or "ap-south-1"
    )
    resolved_model = resolve_model_id(model_id or settings.default_model)
    if timeout is not None:
        limit = float(timeout)
    else:
        configured = float(settings.bedrock_timeout or 0) or 0.0
        # Prefer a long network ceiling over short ERP defaults (30/45/60).
        limit = configured if configured >= 120 else _DEFAULT_NETWORK_TIMEOUT
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
            text = _extract_final_text(response, model_id=resolved_model)
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
        except (
            ClientError,
            BotoCoreError,
            ReadTimeoutError,
            BedrockError,
        ) as exc:
            last_error = exc
            if attempt >= _MAX_RETRIES or not _retryable(exc):
                break
            logger.warning(
                "Bedrock retry | attempt={} | model={} | err={}",
                attempt + 1,
                resolved_model,
                exc,
            )
    if isinstance(last_error, ReadTimeoutError):
        raise BedrockError(f"Bedrock request timed out: {last_error}") from last_error
    raise BedrockError(f"Bedrock request failed: {last_error}") from last_error


def _block_keys(block: Any) -> List[str]:
    if not isinstance(block, dict):
        return [type(block).__name__]
    return sorted(str(k) for k in block.keys())


def _reasoning_text(block: Dict[str, Any]) -> str:
    """Extract diagnostic text from reasoningContent without treating it as the answer."""
    raw = block.get("reasoningContent")
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("text", "reasoningText", "content"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict) and isinstance(val.get("text"), str):
                return str(val.get("text") or "").strip()
    return ""


def _inspect_message(response: Any) -> Dict[str, Any]:
    """Classify Converse message content without logging prompt/workbook data."""
    try:
        message = response["output"]["message"]
        content = message.get("content") if isinstance(message, dict) else None
    except (KeyError, TypeError) as exc:
        raise BedrockMalformedResponse("Unexpected Bedrock response shape") from exc

    blocks = list(content or [])
    text_parts: List[str] = []
    has_reasoning = False
    block_key_sets: List[List[str]] = []
    for block in blocks:
        keys = _block_keys(block)
        block_key_sets.append(keys)
        if not isinstance(block, dict):
            continue
        if block.get("text"):
            text_parts.append(str(block["text"]))
        if "reasoningContent" in block or _reasoning_text(block):
            has_reasoning = True
    text = "\n".join(text_parts).strip()
    usage = response.get("usage") if isinstance(response, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        "text": text,
        "has_text": bool(text),
        "has_reasoning": has_reasoning,
        "block_count": len(blocks),
        "block_keys": block_key_sets,
        "stop_reason": response.get("stopReason") if isinstance(response, dict) else None,
        "input_tokens": int(usage.get("inputTokens") or 0),
        "output_tokens": int(usage.get("outputTokens") or 0),
    }


def _log_no_text_diagnosis(info: Dict[str, Any], *, model_id: str) -> None:
    logger.warning(
        "Bedrock response without final text | model={} | stopReason={} | "
        "block_count={} | block_keys={} | input_tokens={} | output_tokens={} | "
        "has_text={} | has_reasoningContent={}",
        model_id,
        info.get("stop_reason"),
        info.get("block_count"),
        info.get("block_keys"),
        info.get("input_tokens"),
        info.get("output_tokens"),
        info.get("has_text"),
        info.get("has_reasoning"),
    )


def _extract_final_text(response: Any, *, model_id: str) -> str:
    """
    Return the final assistant text answer only.

    reasoningContent is never accepted as the structured answer.
    """
    info = _inspect_message(response)
    if info["has_text"]:
        return str(info["text"])
    _log_no_text_diagnosis(info, model_id=model_id)
    if info["has_reasoning"]:
        raise BedrockReasoningOnly(
            "Bedrock returned reasoningContent without a final text answer"
        )
    if int(info.get("block_count") or 0) == 0:
        raise BedrockEmptyResponse("Bedrock returned an empty response")
    raise BedrockMalformedResponse(
        "Bedrock returned content blocks without extractable text"
    )


def _message_text(response: Any) -> str:
    """Backward-compatible helper used by health checks."""
    return _extract_final_text(response, model_id="")


def probe(model: str, message: str, *, timeout: float = 20.0) -> dict:
    """One health-check call. Credentials stay on the IAM role chain. Never raises."""
    from datetime import datetime, timezone

    from botocore.exceptions import ConnectTimeoutError, EndpointConnectionError

    from app.llm.model_registry import is_known_model

    settings = get_settings()
    region = (
        (settings.bedrock_region or settings.aws_region or "ap-south-1").strip()
        or "ap-south-1"
    )
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).isoformat()
    if not is_known_model(model):
        return {
            "status": "Failed",
            "reply": "Unknown model. Choose a model from the registry.",
            "latency_ms": 0,
            "model": model or "",
            "model_id": "",
            "region": region,
            "timestamp": stamp,
        }
    resolved = resolve_model_id(model)
    text = (message or "Hello").strip() or "Hello"
    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(connect_timeout=10.0, read_timeout=float(timeout), retries={"max_attempts": 1}),
        )
        response = client.converse(
            modelId=resolved,
            messages=[{"role": "user", "content": [{"text": text}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 200},
        )
        try:
            reply = _extract_final_text(response, model_id=resolved) or "Bedrock connection successful."
        except BedrockReasoningOnly:
            reply = "Bedrock connection successful (reasoning-only probe reply)."
        except BedrockError:
            reply = "Bedrock connection successful."
        latency = int(round((time.perf_counter() - started) * 1000))
        logger.info(
            "Bedrock health check | status=Connected | model={} | region={} | latency_ms={}",
            display_name_for(resolved),
            region,
            latency,
        )
        return {
            "status": "Connected",
            "reply": reply,
            "latency_ms": latency,
            "model": display_name_for(resolved),
            "model_id": resolved,
            "region": region,
            "timestamp": stamp,
        }
    except Exception as exc:  # noqa: BLE001
        latency = int(round((time.perf_counter() - started) * 1000))
        status, reply = _probe_failure(exc)
        logger.warning(
            "Bedrock health check | status={} | model={} | region={} | err={}",
            status,
            display_name_for(resolved),
            region,
            exc,
        )
        return {
            "status": status,
            "reply": reply,
            "latency_ms": latency,
            "model": display_name_for(resolved),
            "model_id": resolved,
            "region": region,
            "timestamp": stamp,
        }


def _probe_failure(exc: Exception) -> tuple[str, str]:
    from botocore.exceptions import ConnectTimeoutError, EndpointConnectionError

    if isinstance(exc, (ReadTimeoutError, ConnectTimeoutError, TimeoutError)):
        return "Connection Timeout", "The Bedrock request timed out."
    if isinstance(exc, EndpointConnectionError):
        return "Connection Timeout", "Could not reach the Bedrock endpoint."
    if isinstance(exc, NoCredentialsError):
        return "Authentication Failed", "No IAM credentials were found for this host."
    code = ""
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code") or "")
    folded = f"{code} {exc}".lower()
    if any(token in folded for token in ("accessdenied", "unauthorized", "not authorized", "forbidden")):
        return "Access Denied", "Bedrock denied this model for the current IAM role."
    if any(
        token in folded
        for token in (
            "expiredtoken",
            "unrecognizedclient",
            "invalidclient",
            "signature",
            "nocredentials",
            "security token",
            "unable to locate credentials",
        )
    ):
        return "Authentication Failed", "IAM authentication for Bedrock failed."
    if "timeout" in folded or "timed out" in folded:
        return "Connection Timeout", "The Bedrock request timed out."
    return "Failed", "Bedrock did not complete the health check."


def _retryable(exc: Exception) -> bool:
    """Retry throttling/transient errors only — never retry content-shape failures."""
    if isinstance(exc, NoCredentialsError):
        return False
    if isinstance(
        exc,
        (BedrockEmptyResponse, BedrockReasoningOnly, BedrockMalformedResponse),
    ):
        return False
    if isinstance(exc, BedrockError):
        return False
    if isinstance(exc, ReadTimeoutError):
        return True
    if isinstance(exc, BotoCoreError) and not isinstance(exc, ClientError):
        return True
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code") or "")
        return code in _RETRYABLE
    return False
