"""Registry and Converse health-check routing for the three UAT models."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, NoCredentialsError

from app.llm.bedrock_client import complete, probe
from app.llm.model_registry import (
    default_model,
    is_known_model,
    provider_for,
    public_model_names,
    resolve_model_id,
)


def test_default_model_is_minimax_m2():
    assert default_model().display_name == "MiniMax M2"
    assert default_model().model_id == "minimax.minimax-m2"


def test_resolve_exact_model_ids():
    assert resolve_model_id("MiniMax M2") == "minimax.minimax-m2"
    assert resolve_model_id("GLM 4.7") == "zai.glm-4.7"
    assert resolve_model_id("GLM 4.7 Flash") == "zai.glm-4.7-flash"


def test_all_models_use_converse():
    for name in ("MiniMax M2", "GLM 4.7", "GLM 4.7 Flash"):
        assert provider_for(name) == "converse"


def test_public_model_names_exact():
    assert public_model_names() == ["MiniMax M2", "GLM 4.7", "GLM 4.7 Flash"]


def test_removed_models_are_unknown():
    assert is_known_model("GPT-5.4") is False
    assert is_known_model("GLM 4.5") is False
    assert is_known_model("GLM 4.5 Flash") is False
    assert is_known_model("openai.gpt-5.4") is False
    assert is_known_model("zhipu.glm-4.5") is False


def test_complete_uses_converse_for_all_three():
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{"text": "ok"}]}},
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }
    for name, model_id in (
        ("MiniMax M2", "minimax.minimax-m2"),
        ("GLM 4.7", "zai.glm-4.7"),
        ("GLM 4.7 Flash", "zai.glm-4.7-flash"),
    ):
        runtime.reset_mock()
        with patch("app.llm.bedrock_client.get_bedrock_client", return_value=runtime):
            result = complete(system="sys", user="usr", model_id=name)
        runtime.converse.assert_called_once()
        assert runtime.converse.call_args.kwargs["modelId"] == model_id
        assert result.model_id == model_id


def test_probe_routes_all_three_through_converse():
    for name, model_id in (
        ("MiniMax M2", "minimax.minimax-m2"),
        ("GLM 4.7", "zai.glm-4.7"),
        ("GLM 4.7 Flash", "zai.glm-4.7-flash"),
    ):
        with patch("app.llm.bedrock_client.boto3.client") as client_factory:
            client = MagicMock()
            client.converse.return_value = {
                "output": {"message": {"content": [{"text": "pong"}]}},
            }
            client_factory.return_value = client
            data = probe(name, "Hello")
        client.converse.assert_called_once()
        assert client.converse.call_args.kwargs["modelId"] == model_id
        assert data["status"] == "Connected"
        assert data["model_id"] == model_id
        assert data["model"] == name


def test_probe_maps_auth_and_access_errors():
    with patch(
        "app.llm.bedrock_client.boto3.client",
        side_effect=NoCredentialsError(),
    ):
        auth = probe("MiniMax M2", "Hello")
    assert auth["status"] == "Authentication Failed"

    denied = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}, "ResponseMetadata": {}},
        "Converse",
    )
    with patch("app.llm.bedrock_client.boto3.client") as client_factory:
        client = MagicMock()
        client.converse.side_effect = denied
        client_factory.return_value = client
        access = probe("GLM 4.7", "Hello")
    assert access["status"] == "Access Denied"
