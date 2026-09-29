"""Central Bedrock model registry.

Model ids stay in this module. The rest of the application uses display names
or ``resolve_model_id()``. The first entry is the default.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BedrockModel:
    display_name: str
    model_id: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    provider: str = "converse"


_MODELS: tuple[BedrockModel, ...] = (
    BedrockModel("MiniMax M2", "minimax.minimax-m2", 0.50, 1.50, provider="converse"),
    BedrockModel("GLM 4.7", "zai.glm-4.7", 0.50, 1.50, provider="converse"),
    BedrockModel("GLM 4.7 Flash", "zai.glm-4.7-flash", 0.20, 0.80, provider="converse"),
)


def default_model() -> BedrockModel:
    return _MODELS[0]


def default_model_id() -> str:
    return default_model().model_id


def public_model_names() -> list[str]:
    return [model.display_name for model in _MODELS]


def _match(value: str) -> BedrockModel | None:
    text = value.strip()
    if not text:
        return None
    folded = text.casefold()
    for model in _MODELS:
        if text == model.model_id or folded == model.display_name.casefold():
            return model
    return None


def resolve_model_id(value: str | None) -> str:
    """Map a display name or model id to the Bedrock id. Unknown values use the default."""
    found = _match(value or "")
    return found.model_id if found else default_model_id()


def is_known_model(value: str | None) -> bool:
    return _match(value or "") is not None


def display_name_for(value: str | None) -> str:
    """Friendly name for the UI. Unknown stored values use the default name."""
    found = _match(value or "")
    return found.display_name if found else default_model().display_name


def rates_for(value: str | None) -> tuple[float, float]:
    found = _match(value or "") or default_model()
    return found.input_usd_per_1m, found.output_usd_per_1m


def provider_for(value: str | None) -> str:
    """Return the invocation provider for a display name or model id."""
    found = _match(value or "") or default_model()
    return found.provider
