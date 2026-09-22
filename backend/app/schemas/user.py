"""User request/response schemas."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.enums import OutlookSyncPermission, UserRole
from app.schemas.common import TimestampSchema


class UserBase(BaseModel):
    """Shared user fields (no password)."""

    username: str = Field(..., min_length=3, max_length=100)
    email: str
    full_name: str = Field(..., min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=255)
    role: UserRole = UserRole.USER
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None
    is_active: bool = True
    outlook_sync_permission: OutlookSyncPermission = OutlookSyncPermission.OWN


class UserCreate(BaseModel):
    """Super Admin payload for creating Admin or User accounts."""

    full_name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1)
    role: UserRole = UserRole.USER
    is_active: bool = True
    email: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None
    outlook_sync_permission: Optional[OutlookSyncPermission] = None

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
    email: Optional[str] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=255)
    role: Optional[UserRole] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    department: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    outlook_sync_permission: Optional[OutlookSyncPermission] = None

    @field_validator("role")
    @classmethod
    def role_not_super_admin(cls, value: Optional[UserRole]) -> Optional[UserRole]:
        if value == UserRole.SUPER_ADMIN:
            raise ValueError("Cannot assign Super Admin role to a database user")
        return value


class OutlookSyncPermissionUpdate(BaseModel):
    """Persona Sync Outlook permission (3-state)."""

    outlook_sync_permission: OutlookSyncPermission


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


class RoleUpdate(BaseModel):
    """Promote or demote a database user between admin and sales owner."""

    role: UserRole

    @field_validator("role")
    @classmethod
    def role_must_be_db_role(cls, value: UserRole) -> UserRole:
        if value == UserRole.SUPER_ADMIN:
            raise ValueError("Cannot assign Super Admin role to a database user")
        if value not in {UserRole.ADMIN, UserRole.USER}:
            raise ValueError("Role must be admin or user")
        return value


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
    segments: List[str] = Field(default_factory=list)
    distributor_ids: List[int] = Field(default_factory=list)
    assigned_distributor_count: int = 0
    outlook_sync_permission: OutlookSyncPermission = OutlookSyncPermission.OWN


class SegmentAssign(BaseModel):
    """Replace segment permissions for a user (legacy)."""

    segments: List[str] = Field(default_factory=list)


class DistributorAssign(BaseModel):
    """Replace assigned distributors for a user."""

    distributor_ids: List[int] = Field(default_factory=list)


class AccessModeUpdate(BaseModel):
    """Global Access Control Mode payload."""

    access_mode: str = Field(..., description="segment | distributor")


class AccessModeResponse(BaseModel):
    """Current Access Control Mode."""

    access_mode: str


class MatrixCellUpdate(BaseModel):
    """Payload to toggle a single segment permission for a user in the matrix."""

    user_id: int
    segment: str
    enabled: bool
    # Required when enabled=False (untick confirmation): keep historical visibility?
    retain_history: Optional[bool] = None


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
    email: Optional[str] = None
    segments: List[str] = Field(default_factory=list)
    distributor_ids: List[int] = Field(default_factory=list)
    assigned_distributor_count: int = 0
    access_mode: str = "segment"
    outlook_sync_permission: str = OutlookSyncPermission.OWN.value


class LoginResponse(BaseModel):
    """Login API response."""

    success: bool = True
    data: LoginUserData
    message: str = "Login successful"
