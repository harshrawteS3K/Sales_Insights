"""Authentication service — DB users + .env Super Admin fallback."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.enums import AuditAction, AuditModule, AuditStatus, UserRole
from app.exceptions import UnauthorizedError
from app.repositories.user_repository import UserRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.user import LoginUserData
from app.services.audit_service import AuditService
from app.utils.passwords import normalize_username, verify_password

logger = get_logger(__name__)

SUPER_ADMIN_DISPLAY_NAME = "Super Admin"
SUPER_ADMIN_TITLE = "Identity Administrator"


class AuthService:
    """Authenticate callers without redesigning header/session RBAC."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    def login(self, username: str, password: str) -> LoginUserData:
        """
        Authenticate.

        1. Look up active (non-deleted) database user by username.
        2. If found: require active + valid password hash.
        3. Else: compare against SUPER_ADMIN_USERNAME / SUPER_ADMIN_PASSWORD from .env.
        4. Super Admin is never inserted into the database.
        """
        uname = normalize_username(username)
        if not uname or not password:
            raise UnauthorizedError("Invalid username or password")

        user = self.users.get_by_username(uname)
        if user is not None:
            if not user.is_active:
                self._audit_failed(uname, "Inactive user login attempt")
                raise UnauthorizedError("Account is inactive. Contact the Super Admin.")
            if not verify_password(password, user.password_hash):
                self._audit_failed(uname, "Invalid password")
                raise UnauthorizedError("Invalid username or password")

            role = user.role
            data = LoginUserData(
                role=role,
                name=user.full_name,
                title=user.title or ("Admin" if role == UserRole.ADMIN.value else "User"),
                username=user.username,
                user_id=user.id,
            )
            self.audit.log(
                AuditTrailCreate(
                    user_name=user.full_name,
                    user_role=role,
                    action=AuditAction.LOGIN,
                    details=f"{user.full_name} signed in as {role}",
                    module=AuditModule.AUTHENTICATION.value,
                    status=AuditStatus.INFO.value,
                    entity_type="auth",
                    entity_id=str(user.id),
                    user_id=user.id,
                )
            )
            logger.info("Login success | username={} role={}", user.username, role)
            return data

        # Super Admin — credentials exclusively from environment
        env_user = normalize_username(settings.super_admin_username)
        env_pass = settings.super_admin_password or ""
        if env_user and env_pass and uname == env_user and password == env_pass:
            data = LoginUserData(
                role=UserRole.SUPER_ADMIN.value,
                name=SUPER_ADMIN_DISPLAY_NAME,
                title=SUPER_ADMIN_TITLE,
                username=env_user,
                user_id=None,
            )
            self.audit.log(
                AuditTrailCreate(
                    user_name=SUPER_ADMIN_DISPLAY_NAME,
                    user_role=UserRole.SUPER_ADMIN.value,
                    action="Super Admin Login",
                    details="Super Admin signed in from system credentials",
                    module=AuditModule.AUTHENTICATION.value,
                    status=AuditStatus.INFO.value,
                    entity_type="auth",
                    entity_id="super_admin",
                )
            )
            logger.info("Super Admin login success | username={}", env_user)
            return data

        self._audit_failed(uname, "Unknown username or Super Admin mismatch")
        raise UnauthorizedError("Invalid username or password")

    def _audit_failed(self, username: str, reason: str) -> None:
        try:
            self.audit.log(
                AuditTrailCreate(
                    user_name=username or "unknown",
                    user_role=None,
                    action=AuditAction.FAILED,
                    details=f"Login failed: {reason}",
                    module=AuditModule.AUTHENTICATION.value,
                    status=AuditStatus.FAILED.value,
                    entity_type="auth",
                )
            )
        except Exception:  # noqa: BLE001 — never block login path on audit failure
            logger.warning("Failed to write login-failure audit for {}", username)
