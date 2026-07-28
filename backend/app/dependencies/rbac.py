"""RBAC dependency helpers (Phase 1 – header-based, no JWT)."""

from dataclasses import dataclass
from typing import Annotated, Callable, Optional

from fastapi import Depends, Header, Request

from app.core.config import settings
from app.core.logging import get_logger
from app.enums import UserRole
from app.exceptions import ForbiddenError

logger = get_logger(__name__)


@dataclass
class RequestUser:
    """Caller identity extracted from RBAC headers (JWT-ready shape)."""

    role: UserRole
    name: str
    user_id: Optional[int] = None


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


async def get_current_user(
    request: Request,
    x_user_role: Annotated[Optional[str], Header(alias="X-User-Role")] = None,
    x_user_name: Annotated[Optional[str], Header(alias="X-User-Name")] = None,
    x_user_id: Annotated[Optional[str], Header(alias="X-User-Id")] = None,
) -> RequestUser:
    """
    Resolve the current caller from RBAC headers.

    Phase 1 has no JWT. Endpoints that require authorization use this dependency.
    Defaults to role=user / name=anonymous when headers are absent (dev-friendly).
    """
    role_header = x_user_role or request.headers.get(settings.rbac_role_header)
    name_header = x_user_name or request.headers.get(settings.rbac_user_header)
    id_header = x_user_id or request.headers.get(settings.rbac_user_id_header)

    role = _parse_role(role_header)
    name = (name_header or "anonymous").strip()
    user_id = int(id_header) if id_header and id_header.isdigit() else None

    user = RequestUser(role=role, name=name, user_id=user_id)
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


RequireAdmin = Annotated[RequestUser, Depends(require_roles(UserRole.ADMIN))]
RequireUser = Annotated[RequestUser, Depends(require_roles(UserRole.ADMIN, UserRole.USER))]
CurrentUser = Annotated[RequestUser, Depends(get_current_user)]
