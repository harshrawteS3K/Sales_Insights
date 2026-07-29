"""RBAC dependency helpers — header-based (dev) + production auth modes."""

from dataclasses import dataclass
from typing import Annotated, Callable, Optional

from fastapi import Depends, Header, Request

from app.core.config import settings
from app.core.logging import get_logger
from app.enums import UserRole
from app.exceptions import ForbiddenError, UnauthorizedError

logger = get_logger(__name__)


@dataclass
class RequestUser:
    """Caller identity extracted from RBAC headers / JWT (JWT-ready shape)."""

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


def _auth_mode() -> str:
    return (settings.auth_mode or "headers").strip().lower()


def _verify_trusted_gateway(request: Request) -> None:
    """Require shared secret from corporate reverse proxy / API gateway."""
    secret = (settings.auth_trusted_secret or "").strip()
    if not secret:
        if settings.is_production:
            raise UnauthorizedError(
                "AUTH_TRUSTED_SECRET is required when AUTH_MODE=trusted_headers in production"
            )
        logger.warning(
            "AUTH_MODE=trusted_headers but AUTH_TRUSTED_SECRET is empty — allowing request (non-production)"
        )
        return

    header_name = settings.auth_trusted_header or "X-Internal-Auth"
    provided = request.headers.get(header_name) or request.headers.get(header_name.lower())
    if not provided or provided.strip() != secret:
        logger.warning("Trusted auth failed | missing_or_invalid header={}", header_name)
        raise UnauthorizedError("Missing or invalid internal authentication header")


def _user_from_jwt(request: Request) -> RequestUser:
    """Validate Bearer JWT and map claims to RequestUser."""
    secret = (settings.auth_jwt_secret or "").strip()
    if not secret:
        raise UnauthorizedError("AUTH_JWT_SECRET is not configured for AUTH_MODE=jwt")

    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise UnauthorizedError("Authorization Bearer token required")
    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError("Empty Bearer token")

    try:
        import jwt  # PyJWT
    except ImportError as exc:
        raise UnauthorizedError(
            "PyJWT is required for AUTH_MODE=jwt — install with: pip install PyJWT"
        ) from exc

    options = {"require": ["exp"]}
    decode_kwargs = {
        "algorithms": [settings.auth_jwt_algorithm or "HS256"],
        "options": options,
    }
    audience = (settings.auth_jwt_audience or "").strip()
    if audience:
        decode_kwargs["audience"] = audience

    try:
        claims = jwt.decode(token, secret, **decode_kwargs)
    except Exception as exc:
        logger.warning("JWT validation failed | error={}", exc)
        raise UnauthorizedError("Invalid or expired token") from exc

    role_raw = claims.get("role") or claims.get("roles") or claims.get("app_role")
    if isinstance(role_raw, list):
        role_raw = role_raw[0] if role_raw else None
    name = (
        claims.get("name")
        or claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
        or "jwt-user"
    )
    uid = claims.get("uid") or claims.get("user_id") or claims.get("sub")
    user_id = int(uid) if isinstance(uid, int) or (isinstance(uid, str) and uid.isdigit()) else None
    return RequestUser(role=_parse_role(str(role_raw) if role_raw else None), name=str(name), user_id=user_id)


def _user_from_headers(
    request: Request,
    x_user_role: Optional[str],
    x_user_name: Optional[str],
    x_user_id: Optional[str],
) -> RequestUser:
    role_header = x_user_role or request.headers.get(settings.rbac_role_header)
    name_header = x_user_name or request.headers.get(settings.rbac_user_header)
    id_header = x_user_id or request.headers.get(settings.rbac_user_id_header)

    role = _parse_role(role_header)
    name = (name_header or "anonymous").strip()
    user_id = int(id_header) if id_header and id_header.isdigit() else None
    return RequestUser(role=role, name=name, user_id=user_id)


async def get_current_user(
    request: Request,
    x_user_role: Annotated[Optional[str], Header(alias="X-User-Role")] = None,
    x_user_name: Annotated[Optional[str], Header(alias="X-User-Name")] = None,
    x_user_id: Annotated[Optional[str], Header(alias="X-User-Id")] = None,
) -> RequestUser:
    """
    Resolve the current caller based on AUTH_MODE.

    - headers (default): Phase 1 RBAC headers — preserved for local/dev workflow.
    - trusted_headers: same headers + gateway shared secret (corp network / reverse proxy).
    - jwt: Authorization Bearer JWT; role/name from claims.

    Defaults to role=user / name=anonymous when headers are absent (dev-friendly)
    unless jwt/trusted mode requires credentials.
    """
    mode = _auth_mode()

    if mode == "jwt":
        user = _user_from_jwt(request)
    else:
        if mode == "trusted_headers":
            _verify_trusted_gateway(request)
        elif mode not in {"headers", "header", "dev"}:
            logger.warning("Unknown AUTH_MODE={!r} — falling back to headers", mode)
        user = _user_from_headers(request, x_user_role, x_user_name, x_user_id)

        # Production guard: never silently accept spoofed admin without gateway/JWT.
        if (
            settings.is_production
            and mode in {"headers", "header", "dev"}
            and user.role == UserRole.ADMIN
            and not (settings.auth_trusted_secret or settings.auth_jwt_secret)
        ):
            logger.error(
                "Production AUTH_MODE=headers with admin role and no AUTH_TRUSTED_SECRET/JWT — "
                "configure trusted_headers or jwt before exposing outside the corp network"
            )

    request.state.current_user = user
    logger.debug(
        "Resolved request user | mode={} | role={} | name={}",
        mode,
        user.role.value,
        user.name,
    )
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
