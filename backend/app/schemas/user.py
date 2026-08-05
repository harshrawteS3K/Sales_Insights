"""User request/response schemas."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.enums import UserRole
from app.schemas.common import TimestampSchema


class UserBase(BaseModel):
    """Shared user fields (no password)."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=255)
    role: UserRole = UserRole.USER
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None
    is_active: bool = True


class UserCreate(BaseModel):
    """Super Admin payload for creating Admin or User accounts."""

    full_name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1)
    role: UserRole = UserRole.USER
    is_active: bool = True
    email: Optional[EmailStr] = None
    title: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None

    @field_validator("role")
    @classmethod
    def role_must_be_db_role(cls, value: UserRole) -> UserRole:
        if value == UserRole.SUPER_ADMIN:
            raise ValueError("Cannot create a Super Admin account in the database")
        if value not in {UserRole.ADMIN, UserRole.USER}:
            raise ValueError("Role must be admin or user")
        return value


class UserUpdate(BaseModel):
    """Payload for updating profile fields (Super Admin)."""

    username: Optional[str] = Field(default=None, min_length=3, max_length=100)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=255)
    role: Optional[UserRole] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def role_not_super_admin(cls, value: Optional[UserRole]) -> Optional[UserRole]:
        if value == UserRole.SUPER_ADMIN:
            raise ValueError("Cannot assign Super Admin role to a database user")
        return value


class UsernameUpdate(BaseModel):
    """Change login username."""

    username: str = Field(..., min_length=3, max_length=100)


class PasswordChange(BaseModel):
    """Super Admin assigns a new password (never shows current)."""

    new_password: str = Field(..., min_length=1)
    confirm_password: str = Field(..., min_length=1)


class StatusUpdate(BaseModel):
    """Enable / disable a database user."""

    is_active: bool


class UserResponse(TimestampSchema):
    """User API response — never includes password_hash."""

    id: int
    username: str
    email: EmailStr
    full_name: str
    title: Optional[str] = None
    role: UserRole
    phone: Optional[str] = None
    department: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True
    is_deleted: bool = False


class UserListResponse(BaseModel):
    """List of users."""

    success: bool = True
    data: List[UserResponse]
    total: int


class LoginRequest(BaseModel):
    """Login credentials."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class LoginUserData(BaseModel):
    """Authenticated session payload for the frontend."""

    role: str
    name: str
    title: str
    username: str
    user_id: Optional[int] = None


class LoginResponse(BaseModel):
    """Login API response."""

    success: bool = True
    data: LoginUserData
    message: str = "Login successful"
