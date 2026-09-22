"""User management endpoints — Admin / Super Admin."""

from typing import Optional

from fastapi import APIRouter, Query, status
from fastapi.responses import FileResponse

from app.constants.business_segments import BUSINESS_SEGMENTS
from app.core.logging import get_logger
from app.database.session import get_db
from app.dependencies.rbac import RequireAdmin
from app.dependencies.services import UserServiceDep
from app.repositories.user_segment_repository import UserSegmentRepository
from fastapi import Depends
from sqlalchemy.orm import Session
from app.schemas.common import DataResponse, MessageResponse
from app.schemas.user import (
    AccessModeResponse,
    AccessModeUpdate,
    DistributorAssign,
    OutlookSyncPermissionUpdate,
    PasswordChange,
    MatrixCellUpdate,
    RoleUpdate,
    SegmentAssign,
    StatusUpdate,
    UserCreate,
    UserListResponse,
    UsernameUpdate,
    UserResponse,
    UserUpdate,
)
from app.services.access_control_service import AccessControlService

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)


def _to_response(
    user,
    segments: Optional[list[str]] = None,
    distributor_ids: Optional[list[int]] = None,
) -> UserResponse:
    payload = UserResponse.model_validate(user)
    if segments is not None:
        payload.segments = segments
    if distributor_ids is not None:
        payload.distributor_ids = distributor_ids
        payload.assigned_distributor_count = len(distributor_ids)
    return payload


@router.get("/access-mode", summary="Get Access Control Mode")
def get_access_mode(
    current: RequireAdmin,
    db: Session = Depends(get_db),
) -> DataResponse[AccessModeResponse]:
    _ = current
    mode = AccessControlService(db).get_access_mode()
    return DataResponse(data=AccessModeResponse(access_mode=mode))


@router.put("/access-mode", summary="Set Access Control Mode")
def set_access_mode(
    payload: AccessModeUpdate,
    current: RequireAdmin,
    db: Session = Depends(get_db),
) -> DataResponse[AccessModeResponse]:
    mode = AccessControlService(db).set_access_mode(
        payload.access_mode, actor=current.name
    )
    return DataResponse(
        data=AccessModeResponse(access_mode=mode),
        message=f"Access Control Mode set to '{mode}'",
    )


@router.get("/segments/options", summary="List assignable business segments")
def list_segment_options(_: RequireAdmin) -> DataResponse[list[str]]:
    return DataResponse(data=list(BUSINESS_SEGMENTS))


@router.get("/matrix", summary="Segment permission matrix")
def get_segment_matrix(
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[dict]:
    """GET /api/users/matrix — admin segment permission grid."""
    _ = current
    return DataResponse(data=service.get_segment_matrix())


@router.put("/matrix", summary="Toggle segment permission matrix cell")
def toggle_segment_matrix(
    payload: MatrixCellUpdate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[dict]:
    """PUT /api/users/matrix — enable/disable one user×segment cell."""
    updated = service.toggle_segment_matrix_cell(
        payload.user_id,
        payload.segment,
        payload.enabled,
        actor=current.name,
        assigned_by=current.user_id,
        retain_history=payload.retain_history,
    )
    return DataResponse(
        data={"user_id": payload.user_id, "assigned": updated, "segments": updated},
        message="Segment permission updated",
    )


@router.get("", response_model=UserListResponse, summary="List users (Admin)")
def list_users(
    service: UserServiceDep,
    current: RequireAdmin,
    db: Session = Depends(get_db),
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
    seg_repo = UserSegmentRepository(db)
    return UserListResponse(
        data=[
            _to_response(
                u,
                ["*"] if u.role == "admin" else seg_repo.list_for_user(u.id),
                [] if u.role == "admin" else service.list_distributors_for_user(u.id),
            )
            for u in users
        ],
        total=service.count_users(role=role, status=status_filter, search=search),
    )


@router.get("/export", summary="Export user list to Excel (Admin)")
def export_users(
    service: UserServiceDep,
    current: RequireAdmin,
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
    user_id: int, service: UserServiceDep, current: RequireAdmin
) -> DataResponse[UserResponse]:
    _ = current
    user = service.get_user(user_id)
    segments = (
        ["*"]
        if user.role == "admin"
        else service.list_segments_for_user(user_id)
    )
    dist_ids = (
        []
        if user.role == "admin"
        else service.list_distributors_for_user(user_id)
    )
    return DataResponse(data=_to_response(user, segments, dist_ids))


@router.post(
    "",
    response_model=DataResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Admin or Sales Owner",
)
def create_user(
    payload: UserCreate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    user = service.create_user(payload, actor=current.name)
    return DataResponse(data=_to_response(user, [], []), message="User created")


@router.put("/{user_id}", response_model=DataResponse[UserResponse], summary="Update user")
def update_user(
    user_id: int,
    payload: UserUpdate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    user = service.update_user(user_id, payload, actor=current.name)
    segments = (
        ["*"]
        if user.role == "admin"
        else service.list_segments_for_user(user_id)
    )
    dist_ids = (
        []
        if user.role == "admin"
        else service.list_distributors_for_user(user_id)
    )
    return DataResponse(data=_to_response(user, segments, dist_ids), message="User updated")


@router.put(
    "/{user_id}/outlook-sync-permission",
    response_model=DataResponse[UserResponse],
    summary="Set Sync Outlook permission",
)
def set_outlook_sync_permission(
    user_id: int,
    payload: OutlookSyncPermissionUpdate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    user = service.update_user(
        user_id,
        UserUpdate(outlook_sync_permission=payload.outlook_sync_permission),
        actor=current.name,
    )
    segments = (
        ["*"]
        if user.role == "admin"
        else service.list_segments_for_user(user_id)
    )
    dist_ids = (
        []
        if user.role == "admin"
        else service.list_distributors_for_user(user_id)
    )
    return DataResponse(
        data=_to_response(user, segments, dist_ids),
        message="Sync Outlook permission updated",
    )


@router.put(
    "/{user_id}/username",
    response_model=DataResponse[UserResponse],
    summary="Edit username",
)
def update_username(
    user_id: int,
    payload: UsernameUpdate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    user = service.update_username(user_id, payload, actor=current.name)
    segments = (
        ["*"]
        if user.role == "admin"
        else service.list_segments_for_user(user_id)
    )
    dist_ids = service.list_distributors_for_user(user_id) if user.role != "admin" else []
    return DataResponse(data=_to_response(user, segments, dist_ids), message="Username updated")


@router.put(
    "/{user_id}/password",
    response_model=MessageResponse,
    summary="Change password",
)
def change_password(
    user_id: int,
    payload: PasswordChange,
    service: UserServiceDep,
    current: RequireAdmin,
) -> MessageResponse:
    actor_role = current.role.value if hasattr(current.role, "value") else str(current.role)
    service.change_password(
        user_id, payload, actor=current.name, actor_role=actor_role
    )
    return MessageResponse(message="Password updated")


@router.put(
    "/{user_id}/role",
    response_model=DataResponse[UserResponse],
    summary="Promote or demote user role",
)
def set_role(
    user_id: int,
    payload: RoleUpdate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    actor_role = current.role.value if hasattr(current.role, "value") else str(current.role)
    user = service.set_role(
        user_id, payload, actor=current.name, actor_role=actor_role
    )
    segments = (
        ["*"]
        if user.role == "admin"
        else service.list_segments_for_user(user_id)
    )
    dist_ids = (
        []
        if user.role == "admin"
        else service.list_distributors_for_user(user_id)
    )
    return DataResponse(
        data=_to_response(user, segments, dist_ids),
        message=f"Role updated to {user.role}",
    )


@router.put(
    "/{user_id}/segments",
    response_model=DataResponse[UserResponse],
    summary="Assign segment permissions",
)
def assign_segments(
    user_id: int,
    payload: SegmentAssign,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    user = service.get_user(user_id)
    segments = service.assign_segments(user_id, payload.segments, actor=current.name)
    dist_ids = service.list_distributors_for_user(user_id) if user.role != "admin" else []
    return DataResponse(
        data=_to_response(user, segments if user.role != "admin" else ["*"], dist_ids),
        message="Segments updated",
    )


@router.put(
    "/{user_id}/distributors",
    response_model=DataResponse[UserResponse],
    summary="Assign distributors",
)
def assign_distributors(
    user_id: int,
    payload: DistributorAssign,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    user = service.get_user(user_id)
    dist_ids = service.assign_distributors(
        user_id,
        payload.distributor_ids,
        actor=current.name,
        assigned_by=current.user_id,
    )
    segments = (
        ["*"]
        if user.role == "admin"
        else service.list_segments_for_user(user_id)
    )
    return DataResponse(
        data=_to_response(user, segments, dist_ids),
        message="Distributors updated",
    )


@router.put(
    "/{user_id}/status",
    response_model=DataResponse[UserResponse],
    summary="Enable or disable user",
)
def set_status(
    user_id: int,
    payload: StatusUpdate,
    service: UserServiceDep,
    current: RequireAdmin,
) -> DataResponse[UserResponse]:
    user = service.set_status(user_id, payload, actor=current.name)
    segments = (
        ["*"]
        if user.role == "admin"
        else service.list_segments_for_user(user_id)
    )
    dist_ids = service.list_distributors_for_user(user_id) if user.role != "admin" else []
    return DataResponse(
        data=_to_response(user, segments, dist_ids),
        message="User enabled" if payload.is_active else "User disabled",
    )


@router.delete("/{user_id}", response_model=MessageResponse, summary="Delete user")
def delete_user(
    user_id: int,
    service: UserServiceDep,
    current: RequireAdmin,
) -> MessageResponse:
    service.delete_user(user_id, actor=current.name)
    return MessageResponse(message=f"User {user_id} deleted")
