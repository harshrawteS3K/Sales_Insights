"""Amazon Bedrock client. Credentials come from the IAM role chain.

Converse models use bedrock-runtime. Mantle models (GPT-5.4) use the
OpenAI-compatible Chat Completions endpoint with SigV4.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ReadTimeoutError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.model_registry import display_name_for, provider_for, resolve_model_id

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
_MANTLE_SERVICE = "bedrock-mantle"

_client: Any = None
_client_key: Optional[tuple[str, float]] = None
_mantle_client: Any = None
_mantle_client_key: Optional[tuple[str, float]] = None


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


@dataclass
class _MantleClient:
    """Thin OpenAI-compatible Mantle caller. Signs with the IAM credential chain."""

    region: str
    timeout: float

    @property
    def base_url(self) -> str:
        return f"https://bedrock-mantle.{self.region}.api.aws/openai/v1"

    def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        signed = _sign_mantle_request(
            method="POST",
            url=url,
            body=body,
            headers=headers,
            region=self.region,
        )
        try:
            response = requests.post(
                url,
                data=body.encode("utf-8"),
                headers=signed,
                timeout=(min(10.0, float(self.timeout)), float(self.timeout)),
            )
        except requests.exceptions.Timeout as exc:
            raise ReadTimeoutError(endpoint_url=url) from exc
        except requests.exceptions.ConnectionError as exc:
            raise BedrockError(f"Bedrock Mantle connection failed: {exc}") from exc
        if response.status_code >= 400:
            raise _http_error_to_client_error(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise BedrockError("Bedrock Mantle returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise BedrockError("Unexpected Bedrock Mantle response shape")
        return payload


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


def _get_mantle_client(region: str, timeout: float) -> _MantleClient:
    """One Mantle client per region and timeout. Credentials stay on the IAM chain."""
    global _mantle_client, _mantle_client_key
    key = (region, float(timeout))
    if _mantle_client is not None and _mantle_client_key == key:
        return _mantle_client
    _mantle_client = _MantleClient(region=region, timeout=float(timeout))
    _mantle_client_key = key
    return _mantle_client


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
    selected = model_id or settings.default_model
    resolved_model = resolve_model_id(selected)
    provider = provider_for(selected)
    limit = float(timeout if timeout is not None else settings.bedrock_timeout or 30)
    if provider == "mantle":
        region = _mantle_region(settings)
        return _complete_mantle(
            system=system,
            user=user,
            model_id=resolved_model,
            region=region,
            timeout=limit,
            reason=reason,
        )
    region = (settings.aws_region or "ap-south-1").strip() or "ap-south-1"
    return _complete_converse(
        system=system,
        user=user,
        model_id=resolved_model,
        region=region,
        timeout=limit,
        reason=reason,
    )


def _complete_converse(
    *,
    system: str,
    user: str,
    model_id: str,
    region: str,
    timeout: float,
    reason: str,
) -> BedrockCompletion:
    client = get_bedrock_client(region, timeout)
    started = time.perf_counter()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.converse(
                modelId=model_id,
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
                model_id=model_id,
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
                model_id,
                exc,
            )
    raise BedrockError(f"Bedrock request failed: {last_error}") from last_error


def _complete_mantle(
    *,
    system: str,
    user: str,
    model_id: str,
    region: str,
    timeout: float,
    reason: str,
) -> BedrockCompletion:
    client = _get_mantle_client(region, timeout)
    started = time.perf_counter()
    last_error: Exception | None = None
    messages = [
        {"role": "system", "content": system or ""},
        {"role": "user", "content": user or ""},
    ]

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.chat_completions(
                model=model_id,
                messages=messages,
                max_tokens=800,
                temperature=0.0,
            )
            text = _mantle_message_text(response)
            if not text.strip():
                raise BedrockError("Bedrock returned an empty response")
            input_tokens, output_tokens = _mantle_usage(response)
            result = BedrockCompletion(
                text=text,
                model_id=model_id,
                region=region,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=int(round((time.perf_counter() - started) * 1000)),
            )
            logger.info(
                "LLM Provider: AWS Bedrock Mantle\n"
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
        except (ClientError, BotoCoreError, ReadTimeoutError, NoCredentialsError, BedrockError) as exc:
            last_error = exc
            if attempt >= _MAX_RETRIES or not _retryable(exc):
                break
            logger.warning(
                "Bedrock Mantle retry | attempt={} | model={} | err={}",
                attempt + 1,
                model_id,
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


def _mantle_message_text(response: dict[str, Any]) -> str:
    try:
        choices = response.get("choices") or []
        message = choices[0].get("message") if choices else {}
        content = message.get("content") if isinstance(message, dict) else ""
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise BedrockError("Unexpected Bedrock Mantle response shape") from exc
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _mantle_usage(response: dict[str, Any]) -> tuple[int, int]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)


def _mantle_region(settings: Any) -> str:
    return (
        (getattr(settings, "bedrock_region", None) or settings.aws_region or "ap-south-1")
        .strip()
        or "ap-south-1"
    )


def _sign_mantle_request(
    *,
    method: str,
    url: str,
    body: str,
    headers: dict[str, str],
    region: str,
) -> dict[str, str]:
    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials is None:
        raise NoCredentialsError()
    frozen = credentials.get_frozen_credentials()
    aws_request = AWSRequest(
        method=method,
        url=url,
        data=body.encode("utf-8"),
        headers=dict(headers),
    )
    SigV4Auth(frozen, _MANTLE_SERVICE, region).add_auth(aws_request)
    signed_headers = {key: value for key, value in aws_request.headers.items()}
    # Host must match the Mantle endpoint the request was signed for.
    signed_headers.setdefault("Host", urlparse(url).netloc)
    return signed_headers


def _http_error_to_client_error(response: requests.Response) -> ClientError:
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": (response.text or "")[:300]}
    message = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("code") or "")
        else:
            message = str(payload.get("message") or payload.get("Message") or "")
    if not message:
        message = f"HTTP {response.status_code}"
    code = "AccessDeniedException" if response.status_code in {401, 403} else "ServiceException"
    if response.status_code == 429:
        code = "ThrottlingException"
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": response.status_code},
        },
        "ChatCompletions",
    )


def probe(model: str, message: str, *, timeout: float = 20.0) -> dict:
    """One health-check call. Credentials stay on the IAM role chain. Never raises."""
    from datetime import datetime, timezone

    from app.llm.model_registry import is_known_model

    settings = get_settings()
    region = _mantle_region(settings)
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
    provider = provider_for(model)
    text = (message or "Hello").strip() or "Hello"
    try:
        if provider == "mantle":
            reply = _probe_mantle(resolved, text, region=region, timeout=timeout)
        else:
            reply = _probe_converse(resolved, text, region=region, timeout=timeout)
        latency = int(round((time.perf_counter() - started) * 1000))
        logger.info(
            "Bedrock health check | status=Connected | provider={} | model={} | region={} | latency_ms={}",
            provider,
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
            "Bedrock health check | status={} | provider={} | model={} | region={} | err={}",
            status,
            provider,
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


def _probe_converse(model_id: str, text: str, *, region: str, timeout: float) -> str:
    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(connect_timeout=10.0, read_timeout=float(timeout), retries={"max_attempts": 1}),
    )
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"temperature": 0.0, "maxTokens": 200},
    )
    return _message_text(response) or "Bedrock connection successful."


def _probe_mantle(model_id: str, text: str, *, region: str, timeout: float) -> str:
    client = _get_mantle_client(region, timeout)
    response = client.chat_completions(
        model=model_id,
        messages=[{"role": "user", "content": text}],
        max_tokens=200,
        temperature=0.0,
    )
    return _mantle_message_text(response) or "Bedrock connection successful."


def _probe_failure(exc: Exception) -> tuple[str, str]:
    from botocore.exceptions import ConnectTimeoutError, EndpointConnectionError

    if isinstance(exc, (ReadTimeoutError, ConnectTimeoutError, TimeoutError)):
        return "Connection Timeout", "The Bedrock request timed out."
    if isinstance(exc, requests.exceptions.Timeout):
        return "Connection Timeout", "The Bedrock request timed out."
    if isinstance(exc, EndpointConnectionError):
        return "Connection Timeout", "Could not reach the Bedrock endpoint."
    if isinstance(exc, requests.exceptions.ConnectionError):
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
    if isinstance(exc, NoCredentialsError):
        return False
    if isinstance(exc, (ReadTimeoutError, BedrockError)):
        return not isinstance(exc, BedrockError) or "empty response" in str(exc).lower()
    if isinstance(exc, BotoCoreError) and not isinstance(exc, ClientError):
        return True
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code") or "")
        return code in _RETRYABLE
    return False
