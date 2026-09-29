"""Registry provider routing and Mantle vs Converse paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from app.llm.bedrock_client import BedrockError, complete, probe
from app.llm.model_registry import (
    display_name_for,
    is_known_model,
    provider_for,
    public_model_names,
    rates_for,
    resolve_model_id,
)


def test_gpt54_resolves_to_mantle_provider():
    assert resolve_model_id("GPT-5.4") == "openai.gpt-5.4"
    assert resolve_model_id("openai.gpt-5.4") == "openai.gpt-5.4"
    assert provider_for("GPT-5.4") == "mantle"
    assert provider_for("openai.gpt-5.4") == "mantle"
    assert display_name_for("openai.gpt-5.4") == "GPT-5.4"


def test_existing_models_remain_converse():
    assert provider_for("GLM 4.5") == "converse"
    assert provider_for("GLM 4.5 Flash") == "converse"
    assert provider_for("MiniMax M2") == "converse"
    assert resolve_model_id("GLM 4.5") == "zhipu.glm-4.5"
    assert resolve_model_id("MiniMax M2") == "minimax.m2"


def test_registry_helpers_unchanged_for_unknown_and_pricing():
    assert is_known_model("not-a-model") is False
    assert resolve_model_id("not-a-model") == "openai.gpt-5.4"
    assert provider_for("not-a-model") == "mantle"
    assert rates_for("GPT-5.4") == (0.25, 2.00)
    assert rates_for("GLM 4.5") == (0.50, 1.50)
    assert "GPT-5.4" in public_model_names()


def test_complete_routes_gpt54_through_mantle_not_converse():
    mantle = MagicMock()
    mantle.chat_completions.return_value = {
        "choices": [{"message": {"content": '{"ok":true}'}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4},
    }
    with patch("app.llm.bedrock_client._get_mantle_client", return_value=mantle) as get_mantle:
        with patch("app.llm.bedrock_client.get_bedrock_client") as get_runtime:
            result = complete(system="sys", user="usr", model_id="GPT-5.4", reason="unit")
    get_mantle.assert_called_once()
    get_runtime.assert_not_called()
    mantle.chat_completions.assert_called_once()
    payload = mantle.chat_completions.call_args.kwargs
    assert payload["model"] == "openai.gpt-5.4"
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert result.text == '{"ok":true}'
    assert result.model_id == "openai.gpt-5.4"
    assert result.input_tokens == 11
    assert result.output_tokens == 4


def test_complete_routes_glm_through_converse():
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{"text": "hello"}]}},
        "usage": {"inputTokens": 3, "outputTokens": 2},
    }
    with patch("app.llm.bedrock_client.get_bedrock_client", return_value=runtime) as get_runtime:
        with patch("app.llm.bedrock_client._get_mantle_client") as get_mantle:
            result = complete(system="sys", user="usr", model_id="GLM 4.5")
    get_runtime.assert_called_once()
    get_mantle.assert_not_called()
    runtime.converse.assert_called_once()
    assert result.text == "hello"
    assert result.model_id == "zhipu.glm-4.5"
    assert result.input_tokens == 3
    assert result.output_tokens == 2


def test_probe_gpt54_uses_mantle():
    with patch("app.llm.bedrock_client._probe_mantle", return_value="pong") as mantle:
        with patch("app.llm.bedrock_client._probe_converse") as converse:
            data = probe("GPT-5.4", "Hello")
    mantle.assert_called_once()
    converse.assert_not_called()
    assert data["status"] == "Connected"
    assert data["reply"] == "pong"
    assert data["model"] == "GPT-5.4"
    assert data["model_id"] == "openai.gpt-5.4"


def test_probe_glm_uses_converse():
    with patch("app.llm.bedrock_client._probe_converse", return_value="ok") as converse:
        with patch("app.llm.bedrock_client._probe_mantle") as mantle:
            data = probe("GLM 4.5 Flash", "Hello")
    converse.assert_called_once()
    mantle.assert_not_called()
    assert data["status"] == "Connected"
    assert data["model_id"] == "zhipu.glm-4.5-flash"


def test_probe_maps_auth_and_access_errors():
    with patch("app.llm.bedrock_client._probe_mantle", side_effect=NoCredentialsError()):
        auth = probe("GPT-5.4", "Hello")
    assert auth["status"] == "Authentication Failed"

    denied = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}, "ResponseMetadata": {}},
        "ChatCompletions",
    )
    with patch("app.llm.bedrock_client._probe_mantle", side_effect=denied):
        access = probe("GPT-5.4", "Hello")
    assert access["status"] == "Access Denied"


def test_complete_mantle_raises_bedrock_error_on_empty():
    mantle = MagicMock()
    mantle.chat_completions.return_value = {"choices": [{"message": {"content": ""}}]}
    with patch("app.llm.bedrock_client._get_mantle_client", return_value=mantle):
        with pytest.raises(BedrockError):
            complete(system="sys", user="usr", model_id="GPT-5.4")
