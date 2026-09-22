"""Authentication service — DB users + hardcoded Super Admin fallback."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction, AuditModule, AuditStatus, OutlookSyncPermission, UserRole
from app.exceptions import UnauthorizedError
from app.repositories.user_repository import UserRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.user import LoginUserData
from app.services.audit_service import AuditService
from app.utils.passwords import normalize_username, verify_password

logger = get_logger(__name__)

# Hardcoded Super Admin — never stored in DB, never read from .env
HARDCODED_SUPER_ADMIN_USERNAME = "superadmin"
HARDCODED_SUPER_ADMIN_PASSWORD = "SuPeR@dmin@123"
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
        3. Else: compare against hardcoded Super Admin credentials.
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
            from app.repositories.user_segment_repository import UserSegmentRepository
            from app.repositories.user_distributor_repository import UserDistributorRepository

            segments = (
                ["*"]
                if role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}
                else UserSegmentRepository(self.db).list_for_user(user.id)
            )
            dist_ids = (
                []
                if role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}
                else UserDistributorRepository(self.db).list_ids_for_user(user.id)
            )
            from app.services.access_control_service import AccessControlService

            access_mode = AccessControlService(self.db).get_access_mode()
            sync_perm = (
                getattr(user, "outlook_sync_permission", None)
                or (
                    OutlookSyncPermission.ALL.value
                    if role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}
                    else OutlookSyncPermission.OWN.value
                )
            )
            data = LoginUserData(
                role=role,
                name=user.full_name,
                title=user.title
                or ("Admin" if role == UserRole.ADMIN.value else "Sales Owner"),
                username=user.username,
                user_id=user.id,
                email=user.email,
                segments=segments,
                distributor_ids=dist_ids,
                assigned_distributor_count=len(dist_ids),
                access_mode=access_mode,
                outlook_sync_permission=sync_perm,
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

        # Super Admin — hardcoded system credentials (never from .env / DB)
        if (
            uname == HARDCODED_SUPER_ADMIN_USERNAME
            and password == HARDCODED_SUPER_ADMIN_PASSWORD
        ):
            data = LoginUserData(
                role=UserRole.SUPER_ADMIN.value,
                name=SUPER_ADMIN_DISPLAY_NAME,
                title=SUPER_ADMIN_TITLE,
                username=HARDCODED_SUPER_ADMIN_USERNAME,
                user_id=None,
                segments=["*"],
                distributor_ids=[],
                assigned_distributor_count=0,
                access_mode="segment",
                outlook_sync_permission=OutlookSyncPermission.ALL.value,
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
            logger.info(
                "Super Admin login success | username={}", HARDCODED_SUPER_ADMIN_USERNAME
            )
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
