"""Distributor schemas."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import TimestampSchema


class DistributorBase(BaseModel):
    """Shared distributor fields."""

    name: str = Field(..., min_length=1, max_length=255)
    company: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    region: Optional[str] = Field(default=None, max_length=150)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=20)
    is_active: bool = True
    notes: Optional[str] = None


class DistributorCreate(DistributorBase):
    """Create distributor payload."""

    pass


class DistributorUpdate(BaseModel):
    """Update distributor payload."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    company: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    region: Optional[str] = Field(default=None, max_length=150)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class DistributorResponse(DistributorBase, TimestampSchema):
    """Distributor API response."""

    id: int
    is_deleted: bool = False


class DistributorInfo(BaseModel):
    """Frontend-aligned distributor info shape (Consolidated Data details)."""

    name: str
    company: str
    address: str = ""
    phone: str = ""


class DistributorListResponse(BaseModel):
    """List of distributors."""

    success: bool = True
    data: List[DistributorResponse]
    total: int
