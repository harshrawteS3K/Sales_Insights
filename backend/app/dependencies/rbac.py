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
    segments_raw = claims.get("segments")
    segments: Optional[list[str]] = None
    if isinstance(segments_raw, list):
        segments = [str(s) for s in segments_raw]
    elif isinstance(segments_raw, str) and segments_raw.strip():
        segments = [s.strip() for s in segments_raw.split(",") if s.strip()]
    return RequestUser(
        role=_parse_role(str(role_raw) if role_raw else None),
        name=str(name),
        user_id=user_id,
        segments=segments,
    )


def _parse_segments_header(raw: Optional[str]) -> Optional[list[str]]:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or None


def _user_from_headers(
    request: Request,
    x_user_role: Optional[str],
    x_user_name: Optional[str],
    x_user_id: Optional[str],
    x_user_segments: Optional[str] = None,
    x_user_email: Optional[str] = None,
) -> RequestUser:
    role_header = x_user_role or request.headers.get(settings.rbac_role_header)
    name_header = x_user_name or request.headers.get(settings.rbac_user_header)
    id_header = x_user_id or request.headers.get(settings.rbac_user_id_header)
    seg_header = x_user_segments or request.headers.get("X-User-Segments")
    email_header = x_user_email or request.headers.get("X-User-Email")

    role = _parse_role(role_header)
    name = (name_header or "anonymous").strip()
    user_id = int(id_header) if id_header and id_header.isdigit() else None
    segments = _parse_segments_header(seg_header)
    email = (email_header or "").strip() or None
    return RequestUser(
        role=role, name=name, user_id=user_id, segments=segments, email=email
    )


async def get_current_user(
    request: Request,
    x_user_role: Annotated[Optional[str], Header(alias="X-User-Role")] = None,
    x_user_name: Annotated[Optional[str], Header(alias="X-User-Name")] = None,
    x_user_id: Annotated[Optional[str], Header(alias="X-User-Id")] = None,
    x_user_segments: Annotated[Optional[str], Header(alias="X-User-Segments")] = None,
    x_user_email: Annotated[Optional[str], Header(alias="X-User-Email")] = None,
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
        user = _user_from_headers(
            request, x_user_role, x_user_name, x_user_id, x_user_segments, x_user_email
        )

        # Hydrate segments/email from DB when not sent on headers (persona users)
        if user.user_id and (not user.segments or not user.email):
            try:
                from app.database.session import SessionLocal
                from app.services.segment_access_service import SegmentAccessService
                from app.repositories.user_repository import UserRepository

                db = SessionLocal()
                try:
                    if not user.segments:
                        user.segments = SegmentAccessService(db).segments_for_user(user)
                    if not user.email:
                        row = UserRepository(db).get_by_id(user.user_id)
                        if row:
                            user.email = row.email
                finally:
                    db.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Segment hydrate failed | user_id={} | err={}", user.user_id, exc)
        elif user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and not user.segments:
            user.segments = ["*"]

        # Production guard: never silently accept spoofed elevated roles without gateway/JWT.
        if (
            settings.is_production
            and mode in {"headers", "header", "dev"}
            and user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}
            and not (settings.auth_trusted_secret or settings.auth_jwt_secret)
        ):
            logger.error(
                "Production AUTH_MODE=headers with elevated role and no AUTH_TRUSTED_SECRET/JWT — "
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
