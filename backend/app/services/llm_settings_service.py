"""Admin LLM settings + usage logging (Amazon Bedrock)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.model_registry import (
    display_name_for,
    is_known_model,
    public_model_names,
    rates_for,
    resolve_model_id,
)
from app.models.llm_usage_log import LlmUsageLog
from app.models.system_setting import SystemSetting

logger = get_logger(__name__)

LLM_PROVIDER_KEY = "llm_provider"
LLM_ENABLED_KEY = "llm_enabled"
LLM_MODEL_KEY = "llm_model"

AVAILABLE_PROVIDERS = ["bedrock"]

# Approx USD per 1M tokens — admin cost estimates only. Rates live on the registry.


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = rates_for(model)
    return round((prompt_tokens / 1_000_000.0) * inp + (completion_tokens / 1_000_000.0) * out, 6)


class LlmSettingsService:
    """Read/write LLM prefs from system_settings; fall back to env."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.env = get_settings()

    def _get(self, key: str) -> Optional[str]:
        row = self.db.get(SystemSetting, key)
        if row is None:
            return None
        return (row.value or "").strip() or None

    def _set(self, key: str, value: str) -> None:
        row = self.db.get(SystemSetting, key)
        if row is None:
            self.db.add(SystemSetting(key=key, value=value))
        else:
            row.value = value
        self.db.flush()

    def is_enabled(self) -> bool:
        raw = self._get(LLM_ENABLED_KEY)
        if raw is None:
            return True
        return raw.lower() in {"1", "true", "yes", "on"}

    def get_provider(self) -> str:
        return "bedrock"

    def get_model(self) -> str:
        return resolve_model_id(self._get(LLM_MODEL_KEY) or self.env.default_model)

    def get_api_key(self) -> str:
        return ""

    def get_settings_payload(self) -> Dict[str, Any]:
        key = self.get_api_key()
        masked = ""
        if key:
            masked = (key[:3] + "…" + key[-4:]) if len(key) > 8 else "••••"
        return {
            "provider": self.get_provider(),
            "enabled": self.is_enabled(),
            "model": display_name_for(self.get_model()),
            "api_key_configured": bool(key),
            "api_key_masked": masked,
            "available_providers": AVAILABLE_PROVIDERS,
            "available_models": public_model_names(),
            "timeout_seconds": float(self.env.bedrock_timeout or 30),
        }

    def update_settings(
        self,
        *,
        provider: Optional[str] = None,
        enabled: Optional[bool] = None,
        model: Optional[str] = None,
        actor: str = "admin",
    ) -> Dict[str, Any]:
        if provider is not None:
            p = provider.strip().lower()
            if p not in AVAILABLE_PROVIDERS:
                from app.exceptions import ValidationAppError

                raise ValidationAppError(
                    f"Unsupported LLM provider '{provider}'",
                    details={"allowed": AVAILABLE_PROVIDERS},
                )
            self._set(LLM_PROVIDER_KEY, p)
        if enabled is not None:
            self._set(LLM_ENABLED_KEY, "true" if enabled else "false")
        if model is not None:
            if not is_known_model(model):
                from app.exceptions import ValidationAppError

                raise ValidationAppError(
                    f"Unsupported model '{model}'",
                    details={"allowed": public_model_names()},
                )
            self._set(LLM_MODEL_KEY, resolve_model_id(model))
        logger.info(
            "LLM settings updated | actor={} | provider={} | enabled={} | model={}",
            actor,
            self.get_provider(),
            self.is_enabled(),
            self.get_model(),
        )
        return self.get_settings_payload()

    def record_usage(
        self,
        *,
        purpose: str,
        usage: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        email_id: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> Optional[LlmUsageLog]:
        usage = usage or {}
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion))
        if total <= 0 and prompt <= 0 and completion <= 0:
            return None
        mdl = model or self.get_model()
        prov = provider or self.get_provider()
        row = LlmUsageLog(
            provider=prov,
            model=mdl,
            purpose=purpose,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            estimated_cost_usd=estimate_cost_usd(mdl, prompt, completion),
            email_id=email_id,
            actor=actor,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def usage_summary(self, *, limit: int = 50) -> Dict[str, Any]:
        totals = self.db.execute(
            select(
                func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0),
                func.coalesce(func.sum(LlmUsageLog.total_tokens), 0),
                func.coalesce(func.sum(LlmUsageLog.estimated_cost_usd), 0.0),
                func.count(LlmUsageLog.id),
            )
        ).one()
        recent = list(
            self.db.scalars(
                select(LlmUsageLog).order_by(LlmUsageLog.created_at.desc()).limit(limit)
            ).all()
        )
        return {
            "totals": {
                "prompt_tokens": int(totals[0] or 0),
                "completion_tokens": int(totals[1] or 0),
                "total_tokens": int(totals[2] or 0),
                "estimated_cost_usd": round(float(totals[3] or 0), 6),
                "calls": int(totals[4] or 0),
            },
            "recent": [
                {
                    "id": r.id,
                    "provider": r.provider,
                    "model": display_name_for(r.model),
                    "purpose": r.purpose,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens,
                    "estimated_cost_usd": r.estimated_cost_usd,
                    "email_id": r.email_id,
                    "actor": r.actor,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in recent
            ],
        }


def resolve_runtime_llm(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Resolve enabled/model/api_key for ERP parsers.

    When ``db`` is provided, admin SystemSetting overrides apply.
    """
    env = get_settings()
    if db is None:
        return {
            "enabled": True,
            "provider": "bedrock",
            "model": resolve_model_id(env.default_model),
            "timeout": float(env.bedrock_timeout or 30),
        }
    svc = LlmSettingsService(db)
    return {
        "enabled": svc.is_enabled(),
        "provider": "bedrock",
        "model": svc.get_model(),
        "timeout": float(env.bedrock_timeout or 30),
    }
