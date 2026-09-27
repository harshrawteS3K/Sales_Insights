"""RBAC dependency helpers. Identity comes from the server session, never from headers."""

import hashlib
from dataclasses import dataclass
from typing import Annotated, Callable, Optional

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.session import get_db
from app.enums import UserRole
from app.exceptions import ForbiddenError, UnauthorizedError
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.auth_service import SESSION_COOKIE_NAME
from app.utils.datetime_utils import utc_now

logger = get_logger(__name__)


@dataclass
class RequestUser:
    """Caller identity loaded from the users table."""

    role: UserRole
    name: str
    user_id: Optional[int] = None
    segments: Optional[list[str]] = None
    email: Optional[str] = None
    distributor_ids: Optional[list[int]] = None


def _parse_role(raw: Optional[str]) -> UserRole:
    if not raw:
        return UserRole.USER
    normalized = raw.strip().lower()
    try:
        return UserRole(normalized)
    except ValueError as exc:
        raise ForbiddenError(
            f"Invalid role '{raw}'. Allowed: {[r.value for r in UserRole]}"
        ) from exc


def _request_user_from_row(db: Session, row: User) -> RequestUser:
    """Build the caller from the database row. Client headers are not consulted."""
    from app.repositories.user_distributor_repository import UserDistributorRepository
    from app.services.segment_access_service import SegmentAccessService

    role = _parse_role(row.role)
    user = RequestUser(
        role=role,
        name=row.full_name,
        user_id=row.id,
        email=row.email,
    )
    user.segments = SegmentAccessService(db).segments_for_user(user)
    if role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        user.distributor_ids = []
    else:
        user.distributor_ids = UserDistributorRepository(db).list_ids_for_user(row.id)
    return user


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> RequestUser:
    """
    Resolve the caller from the login session cookie and the users table.

    ``X-User-Role``, ``X-Role``, and any other client permission field are ignored.
    """
    token = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if not token:
        raise UnauthorizedError("Authentication required")

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == digest,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utc_now(),
        )
    )
    if session is None:
        raise UnauthorizedError("Authentication required")

    row = db.get(User, session.user_id)
    if row is None or row.is_deleted or not row.is_active:
        raise UnauthorizedError("Authentication required")

    user = _request_user_from_row(db, row)
    request.state.current_user = user
    logger.debug("Resolved request user | role={} | name={}", user.role.value, user.name)
    return user


def require_roles(*allowed_roles: UserRole) -> Callable:
    """
    Dependency factory enforcing that the caller has one of the allowed roles.

    Usage::

        @router.post(..., dependencies=[Depends(require_roles(UserRole.ADMIN))])
    """

    allowed = {role if isinstance(role, UserRole) else UserRole(role) for role in allowed_roles}

    async def _dependency(user: Annotated[RequestUser, Depends(get_current_user)]) -> RequestUser:
        if user.role not in allowed:
            logger.warning(
                "RBAC denied | user={} role={} allowed={}",
                user.name,
                user.role.value,
                [r.value for r in allowed],
            )
            raise ForbiddenError(
                f"Role '{user.role.value}' is not permitted for this endpoint",
                details={"allowed_roles": [r.value for r in allowed]},
            )
        return user

    return _dependency


RequireSuperAdmin = Annotated[RequestUser, Depends(require_roles(UserRole.SUPER_ADMIN))]
RequireAdmin = Annotated[
    RequestUser,
    Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)),
]
RequireUser = Annotated[
    RequestUser,
    Depends(require_roles(UserRole.ADMIN, UserRole.USER, UserRole.SUPER_ADMIN)),
]
CurrentUser = Annotated[RequestUser, Depends(get_current_user)]


def segment_scope_for_user(user: RequestUser, db) -> Optional[list[str]]:
    """Resolved segment list for backend data filters (``None`` = all)."""
    from app.services.access_control_service import AccessControlService

    scope = AccessControlService(db).resolve_scope(user)
    if scope.unrestricted:
        return None
    if scope.access_mode == "distributor":
        # Distributor mode does not filter by segment
        return None
    return scope.allowed_segments


def distributor_companies_scope_for_user(user: RequestUser, db) -> Optional[list[str]]:
    """
    Resolved distributor company list for backend filters.

    ``None`` = unrestricted (admin / super admin / segment mode).
    ``[]`` = no distributor access.
    """
    from app.services.access_control_service import AccessControlService

    scope = AccessControlService(db).resolve_scope(user)
    if scope.unrestricted:
        return None
    if scope.access_mode != "distributor":
        return None
    return scope.allowed_companies or []


def data_scope_for_user(user: RequestUser, db):
    """Full DataScope for the current user under global Access Control Mode."""
    from app.services.access_control_service import AccessControlService

    return AccessControlService(db).resolve_scope(user)
