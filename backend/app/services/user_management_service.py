"""User management service — Super Admin identity administration."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.enums import AuditAction, AuditModule, AuditStatus, UserRole
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.user import PasswordChange, StatusUpdate, UserCreate, UsernameUpdate, UserUpdate
from app.services.audit_service import AuditService
from app.utils.files import ensure_dir
from app.utils.passwords import (
    hash_password,
    is_valid_username,
    normalize_username,
    validate_password_pair,
    validate_password_strength,
)

logger = get_logger(__name__)


class UserManagementService:
    """Identity administration over database users (Super Admin only)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    def list_users(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        role: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[User]:
        is_active = self._parse_status(status)
        return self.users.list_identity(
            skip=skip,
            limit=limit,
            role=role,
            is_active=is_active,
            search=search,
        )

    def count_users(
        self,
        *,
        role: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        is_active = self._parse_status(status)
        return self.users.count_identity(role=role, is_active=is_active, search=search)

    def get_user(self, user_id: int) -> User:
        return self.users.get_or_raise(user_id)

    def create_user(self, payload: UserCreate, *, actor: str) -> User:
        ok, username_or_err = is_valid_username(payload.username)
        if not ok:
            raise ValidationAppError(username_or_err)
        username = username_or_err

        # Never collide with Super Admin env username
        if username == normalize_username(settings.super_admin_username):
            raise ConflictError("Username is reserved for the system Super Admin")

        if self.users.get_by_username(username):
            raise ConflictError(f"Username '{username}' is already taken")

        validate_password_strength(payload.password)

        email = (
            str(payload.email).lower()
            if payload.email
            else f"{username}@apcotex.local"
        )
        if self.users.get_by_email(email):
            raise ConflictError(f"Email {email} is already in use")

        role = payload.role.value if hasattr(payload.role, "value") else str(payload.role)
        if role == UserRole.SUPER_ADMIN.value:
            raise ForbiddenError("Cannot create a Super Admin in the database")

        entity = User(
            username=username,
            email=email,
            full_name=payload.full_name.strip(),
            title=payload.title,
            password_hash=hash_password(payload.password),
            role=role,
            phone=payload.phone,
            department=payload.department,
            notes=payload.notes,
            is_active=payload.is_active,
        )
        created = self.users.create(entity)

        action_label = "Created Admin" if role == UserRole.ADMIN.value else "Created User"
        self._audit(
            actor=actor,
            action=action_label,
            description=f'Super Admin created {role} "{created.full_name}"',
            affected=created,
            status=AuditStatus.SUCCESS.value,
        )
        logger.info("Created user id={} username={} role={}", created.id, created.username, role)
        return created

    def update_user(self, user_id: int, payload: UserUpdate, *, actor: str) -> User:
        user = self.users.get_or_raise(user_id)
        data = payload.model_dump(exclude_unset=True)

        if "username" in data and data["username"]:
            ok, username_or_err = is_valid_username(data["username"])
            if not ok:
                raise ValidationAppError(username_or_err)
            username = username_or_err
            if username == normalize_username(settings.super_admin_username):
                raise ConflictError("Username is reserved for the system Super Admin")
            conflict = self.users.get_by_username(username)
            if conflict and conflict.id != user_id:
                raise ConflictError(f"Username '{username}' is already taken")
            data["username"] = username

        if "email" in data and data["email"]:
            data["email"] = str(data["email"]).lower()
            conflict = self.users.get_by_email(data["email"])
            if conflict and conflict.id != user_id:
                raise ConflictError(f"User with email {data['email']} already exists")

        if "role" in data and data["role"] is not None:
            role = data["role"]
            role_val = role.value if hasattr(role, "value") else str(role)
            if role_val == UserRole.SUPER_ADMIN.value:
                raise ForbiddenError("Cannot assign Super Admin role to a database user")
            data["role"] = role_val

        old_username = user.username
        updated = self.users.update(user, data)

        if "username" in data and data["username"] != old_username:
            self._audit(
                actor=actor,
                action="Updated Username",
                description=(
                    f'Super Admin changed username for {updated.role} '
                    f'"{updated.full_name}" from "{old_username}" to "{updated.username}"'
                ),
                affected=updated,
            )
        else:
            self._audit(
                actor=actor,
                action=AuditAction.UPDATED,
                description=f'Super Admin updated user "{updated.full_name}"',
                affected=updated,
            )
        return updated

    def update_username(self, user_id: int, payload: UsernameUpdate, *, actor: str) -> User:
        return self.update_user(user_id, UserUpdate(username=payload.username), actor=actor)

    def change_password(self, user_id: int, payload: PasswordChange, *, actor: str) -> User:
        user = self.users.get_or_raise(user_id)
        validate_password_pair(payload.new_password, payload.confirm_password)
        updated = self.users.update(user, {"password_hash": hash_password(payload.new_password)})
        self._audit(
            actor=actor,
            action="Changed Password",
            description=f'Super Admin changed password for {updated.role} "{updated.full_name}"',
            affected=updated,
        )
        return updated

    def set_status(self, user_id: int, payload: StatusUpdate, *, actor: str) -> User:
        user = self.users.get_or_raise(user_id)
        updated = self.users.update(user, {"is_active": payload.is_active})
        verb = "Enabled" if payload.is_active else "Disabled"
        self._audit(
            actor=actor,
            action=f"{verb} User",
            description=f'Super Admin {verb.lower()} {updated.role} "{updated.full_name}"',
            affected=updated,
        )
        return updated

    def delete_user(self, user_id: int, *, actor: str) -> User:
        user = self.users.get_or_raise(user_id)
        if user.role == UserRole.SUPER_ADMIN.value:
            raise ForbiddenError("Cannot delete the Super Admin")
        snapshot_name = user.full_name
        snapshot_role = user.role
        deleted = self.users.soft_delete(user)
        self._audit(
            actor=actor,
            action="Deleted User",
            description=f'Super Admin deleted {snapshot_role} "{snapshot_name}"',
            affected=deleted,
            status=AuditStatus.WARNING.value,
        )
        return deleted

    def export_excel(
        self,
        *,
        role: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        actor: str = "Super Admin",
    ) -> Path:
        users = self.list_users(skip=0, limit=10000, role=role, status=status, search=search)
        wb = Workbook()
        ws = wb.active
        ws.title = "Users"
        ws.append(["Username", "Full Name", "Email", "Role", "Status", "Title", "Department"])
        for u in users:
            ws.append(
                [
                    u.username,
                    u.full_name,
                    u.email,
                    u.role,
                    "Active" if u.is_active else "Inactive",
                    u.title or "",
                    u.department or "",
                ]
            )
        out_dir = Path(settings.download_dir) / "user_exports"
        ensure_dir(out_dir)
        path = out_dir / f"users_{date.today().isoformat()}.xlsx"
        wb.save(path)
        self._audit(
            actor=actor,
            action="Exported User List",
            description=f"Super Admin exported user list ({len(users)} rows)",
            affected=None,
            entity_id="export",
        )
        return path

    def _audit(
        self,
        *,
        actor: str,
        action: str | AuditAction,
        description: str,
        affected: Optional[User],
        status: str = AuditStatus.SUCCESS.value,
        entity_id: Optional[str] = None,
    ) -> None:
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                user_role=UserRole.SUPER_ADMIN.value,
                action=action,
                details=description,
                module=AuditModule.USER_MANAGEMENT.value,
                status=status,
                entity_type="user",
                entity_id=entity_id or (str(affected.id) if affected else None),
                user_id=affected.id if affected else None,
                extra_metadata={
                    "affected_user": affected.full_name if affected else None,
                    "affected_username": affected.username if affected else None,
                    "affected_role": affected.role if affected else None,
                }
                if affected
                else None,
            )
        )

    @staticmethod
    def _parse_status(status: Optional[str]) -> Optional[bool]:
        if not status:
            return None
        normalized = status.strip().lower()
        if normalized in {"active", "true", "1", "enabled"}:
            return True
        if normalized in {"inactive", "false", "0", "disabled"}:
            return False
        raise ValidationAppError("Status filter must be Active or Inactive")


# Backward-compatible thin wrapper used by older imports / tests
class UserService(UserManagementService):
    """Alias preserving UserService name for dependency injection."""

    def list_users(  # type: ignore[override]
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        role: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[User]:
        return super().list_users(skip=skip, limit=limit, role=role, status=status, search=search)

    def count_users(  # type: ignore[override]
        self,
        *,
        role: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        return super().count_users(role=role, status=status, search=search)

    def create_user(self, payload: UserCreate, *, actor: str = "system") -> User:  # type: ignore[override]
        return super().create_user(payload, actor=actor)

    def update_user(self, user_id: int, payload: UserUpdate, *, actor: str = "system") -> User:  # type: ignore[override]
        return super().update_user(user_id, payload, actor=actor)

    def delete_user(self, user_id: int, *, actor: str = "system") -> User:  # type: ignore[override]
        return super().delete_user(user_id, actor=actor)
