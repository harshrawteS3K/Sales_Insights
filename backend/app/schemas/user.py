"""User request/response schemas."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.enums import UserRole
from app.schemas.common import TimestampSchema


class UserBase(BaseModel):
    """Shared user fields."""

    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=255)
    role: UserRole = UserRole.USER
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    """Payload for creating a user."""

    pass


class UserUpdate(BaseModel):
    """Payload for updating a user."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=255)
    role: Optional[UserRole] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase, TimestampSchema):
    """User API response."""

    id: int
    is_deleted: bool = False


class UserListResponse(BaseModel):
    """List of users."""

    success: bool = True
    data: List[UserResponse]
    total: int
