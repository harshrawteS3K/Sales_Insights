"""Admin Settings — LLM provider / model / usage."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.rbac import RequireAdmin
from app.schemas.common import DataResponse
from app.services.llm_settings_service import LlmSettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])


class LlmSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    enabled: Optional[bool] = None
    model: Optional[str] = Field(default=None, max_length=100)


@router.get("/llm", summary="Get LLM settings (Admin)")
def get_llm_settings(
    current: RequireAdmin,
    db: Session = Depends(get_db),
) -> DataResponse[dict]:
    _ = current
    data = LlmSettingsService(db).get_settings_payload()
    return DataResponse(data=data)


@router.put("/llm", summary="Update LLM settings (Admin)")
def update_llm_settings(
    payload: LlmSettingsUpdate,
    current: RequireAdmin,
    db: Session = Depends(get_db),
) -> DataResponse[dict]:
    data = LlmSettingsService(db).update_settings(
        provider=payload.provider,
        enabled=payload.enabled,
        model=payload.model,
        actor=current.name,
    )
    return DataResponse(data=data, message="LLM settings updated")


@router.get("/llm/usage", summary="LLM token usage & cost (Admin)")
def get_llm_usage(
    current: RequireAdmin,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> DataResponse[dict]:
    _ = current
    data = LlmSettingsService(db).usage_summary(limit=limit)
    return DataResponse(data=data)
