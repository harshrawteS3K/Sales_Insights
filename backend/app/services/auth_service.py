"""Authentication service — database users only, including Super Admin."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction, AuditModule, AuditStatus, OutlookSyncPermission, UserRole
from app.exceptions import UnauthorizedError
from app.models.auth_session import AuthSession
from app.repositories.user_repository import UserRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.user import LoginUserData
from app.services.audit_service import AuditService
from app.utils.datetime_utils import utc_now
from app.utils.passwords import normalize_username, verify_password

logger = get_logger(__name__)

SESSION_COOKIE_NAME = "apcotex_sid"
SESSION_TTL_HOURS = 12

# Username reserved for the seeded Super Admin. The password is never stored here.
RESERVED_SUPER_ADMIN_USERNAME = "superadmin"


class AuthService:
    """Authenticate callers against PostgreSQL and issue a server session."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    def login(self, username: str, password: str) -> tuple[LoginUserData, str]:
        """
        Validate username and bcrypt password, then issue a session token.

        Super Admin uses this same path. There is no separate credential check.
        """
        uname = normalize_username(username)
        if not uname or not password:
            raise UnauthorizedError("Invalid username or password")

        user = self.users.get_by_username(uname)
        if user is None:
            self._audit_failed(uname, "Unknown username")
            raise UnauthorizedError("Invalid username or password")
        if not user.is_active:
            self._audit_failed(uname, "Inactive user login attempt")
            raise UnauthorizedError("Account is inactive. Contact the Super Admin.")
        if not verify_password(password, user.password_hash):
            self._audit_failed(uname, "Invalid password")
            raise UnauthorizedError("Invalid username or password")

        role = user.role
        from app.repositories.user_distributor_repository import UserDistributorRepository
        from app.repositories.user_segment_repository import UserSegmentRepository
        from app.services.access_control_service import AccessControlService

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
            title=user.title or ("Admin" if role == UserRole.ADMIN.value else "Sales Owner"),
            username=user.username,
            user_id=user.id,
            email=user.email,
            segments=segments,
            distributor_ids=dist_ids,
            assigned_distributor_count=len(dist_ids),
            access_mode=access_mode,
            outlook_sync_permission=sync_perm,
        )
        token = self.issue_session(user.id)
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
        return data, token

    def issue_session(self, user_id: int) -> str:
        """Create a random session token and store only its SHA-256 hash."""
        token = secrets.token_urlsafe(32)
        row = AuthSession(
            user_id=user_id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=utc_now() + timedelta(hours=SESSION_TTL_HOURS),
        )
        self.db.add(row)
        self.db.flush()
        return token

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
