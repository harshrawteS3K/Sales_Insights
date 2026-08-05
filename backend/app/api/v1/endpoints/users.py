"""User management endpoints — Super Admin only."""

from typing import Optional

from fastapi import APIRouter, Query, status
from fastapi.responses import FileResponse

from app.core.logging import get_logger
from app.dependencies.rbac import RequireSuperAdmin
from app.dependencies.services import UserServiceDep
from app.schemas.common import DataResponse, MessageResponse
from app.schemas.user import (
    PasswordChange,
    StatusUpdate,
    UserCreate,
    UserListResponse,
    UsernameUpdate,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)


def _to_response(user) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("", response_model=UserListResponse, summary="List users (Super Admin)")
def list_users(
    service: UserServiceDep,
    current: RequireSuperAdmin,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    role: Optional[str] = Query(None, description="admin | user"),
    status_filter: Optional[str] = Query(None, alias="status", description="Active | Inactive"),
    search: Optional[str] = Query(None),
) -> UserListResponse:
    """List all database users for identity management."""
    _ = current
    users = service.list_users(
        skip=skip, limit=limit, role=role, status=status_filter, search=search
    )
    return UserListResponse(
        data=[_to_response(u) for u in users],
        total=service.count_users(role=role, status=status_filter, search=search),
    )


@router.get("/export", summary="Export user list to Excel (Super Admin)")
def export_users(
    service: UserServiceDep,
    current: RequireSuperAdmin,
    role: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
) -> FileResponse:
    path = service.export_excel(
        role=role,
        status=status_filter,
        search=search,
        actor=current.name,
    )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@router.get("/{user_id}", response_model=DataResponse[UserResponse], summary="Get user")
def get_user(
    user_id: int, service: UserServiceDep, current: RequireSuperAdmin
) -> DataResponse[UserResponse]:
    _ = current
    user = service.get_user(user_id)
    return DataResponse(data=_to_response(user))


@router.post(
    "",
    response_model=DataResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Admin or User",
)
def create_user(
    payload: UserCreate,
    service: UserServiceDep,
    current: RequireSuperAdmin,
) -> DataResponse[UserResponse]:
    user = service.create_user(payload, actor=current.name)
    return DataResponse(data=_to_response(user), message="User created")


@router.put("/{user_id}", response_model=DataResponse[UserResponse], summary="Update user")
def update_user(
    user_id: int,
    payload: UserUpdate,
    service: UserServiceDep,
    current: RequireSuperAdmin,
) -> DataResponse[UserResponse]:
    user = service.update_user(user_id, payload, actor=current.name)
    return DataResponse(data=_to_response(user), message="User updated")


@router.put(
    "/{user_id}/username",
    response_model=DataResponse[UserResponse],
    summary="Edit username",
)
def update_username(
    user_id: int,
    payload: UsernameUpdate,
    service: UserServiceDep,
    current: RequireSuperAdmin,
) -> DataResponse[UserResponse]:
    user = service.update_username(user_id, payload, actor=current.name)
    return DataResponse(data=_to_response(user), message="Username updated")


@router.put(
    "/{user_id}/password",
    response_model=MessageResponse,
    summary="Change password",
)
def change_password(
    user_id: int,
    payload: PasswordChange,
    service: UserServiceDep,
    current: RequireSuperAdmin,
) -> MessageResponse:
    service.change_password(user_id, payload, actor=current.name)
    return MessageResponse(message="Password updated")


@router.put(
    "/{user_id}/status",
    response_model=DataResponse[UserResponse],
    summary="Enable or disable user",
)
def set_status(
    user_id: int,
    payload: StatusUpdate,
    service: UserServiceDep,
    current: RequireSuperAdmin,
) -> DataResponse[UserResponse]:
    user = service.set_status(user_id, payload, actor=current.name)
    return DataResponse(
        data=_to_response(user),
        message="User enabled" if payload.is_active else "User disabled",
    )


@router.delete("/{user_id}", response_model=MessageResponse, summary="Delete user")
def delete_user(
    user_id: int,
    service: UserServiceDep,
    current: RequireSuperAdmin,
) -> MessageResponse:
    service.delete_user(user_id, actor=current.name)
    return MessageResponse(message=f"User {user_id} deleted")
