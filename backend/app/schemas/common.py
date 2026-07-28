"""Common response and pagination schemas."""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base schema with ORM mode enabled."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Simple message response."""

    success: bool = True
    message: str


class ErrorDetail(BaseModel):
    """Structured error payload."""

    code: str
    message: str
    details: Optional[Any] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    success: bool = False
    error: ErrorDetail


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list response."""

    success: bool = True
    data: List[T]
    meta: PaginationMeta


class DataResponse(BaseModel, Generic[T]):
    """Generic single-payload response."""

    success: bool = True
    data: T
    message: Optional[str] = None


class TimestampSchema(ORMModel):
    """Created/updated timestamps."""

    created_at: datetime
    updated_at: datetime
