"""User management endpoints."""

from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.logging import get_logger
from app.dependencies.rbac import CurrentUser, RequireAdmin
from app.dependencies.services import UserServiceDep
from app.schemas.common import DataResponse, MessageResponse
from app.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)


@router.get("", response_model=UserListResponse, summary="List users")
def list_users(
    service: UserServiceDep,
    _: RequireAdmin,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> UserListResponse:
    """List users (Admin only)."""
    users = service.list_users(skip=skip, limit=limit, role=role, search=search)
    return UserListResponse(
        data=[UserResponse.model_validate(u) for u in users],
        total=service.count_users(role=role, search=search),
    )


@router.get("/{user_id}", response_model=DataResponse[UserResponse], summary="Get user")
def get_user(user_id: int, service: UserServiceDep, _: RequireAdmin) -> DataResponse[UserResponse]:
    """Get a user by id (Admin only)."""
    user = service.get_user(user_id)
    return DataResponse(data=UserResponse.model_validate(user))


@router.post(
    "",
    response_model=DataResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
)
def create_user(
    payload: UserCreate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    """Create a user (Admin only)."""
    user = service.create_user(payload, actor=current.name)
    return DataResponse(data=UserResponse.model_validate(user), message="User created")


@router.put("/{user_id}", response_model=DataResponse[UserResponse], summary="Update user")
def update_user(
    user_id: int,
    payload: UserUpdate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    """Update a user (Admin only)."""
    user = service.update_user(user_id, payload, actor=current.name)
    return DataResponse(data=UserResponse.model_validate(user), message="User updated")


@router.delete("/{user_id}", response_model=MessageResponse, summary="Delete user")
def delete_user(
    user_id: int,
    service: UserServiceDep,
    current: RequireAdmin,
) -> MessageResponse:
    """Soft-delete a user (Admin only)."""
    service.delete_user(user_id, actor=current.name)
    return MessageResponse(message=f"User {user_id} deleted")
