"""User management service — Super Admin identity administration."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.enums import AuditAction, AuditModule, AuditStatus, OutlookSyncPermission, UserRole
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.user_segment_repository import UserSegmentRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.user import PasswordChange, RoleUpdate, StatusUpdate, UserCreate, UsernameUpdate, UserUpdate
from app.services.audit_service import AuditService
from app.services.auth_service import HARDCODED_SUPER_ADMIN_USERNAME
from app.utils.files import ensure_dir
from app.utils.passwords import (
    hash_password,
    is_valid_username,
    normalize_username,
    validate_password_pair,
    validate_password_strength,
)

logger = get_logger(__name__)


from app.repositories.user_distributor_repository import UserDistributorRepository


class UserManagementService:
    """Identity administration over database users (Admin only)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.user_segments = UserSegmentRepository(db)
        self.user_distributors = UserDistributorRepository(db)
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
        users = self.users.list_identity(
            skip=skip,
            limit=limit,
            role=role,
            is_active=is_active,
            search=search,
        )
        # Sanitize any legacy @apcotex.local emails to valid domain @apcotex.com
        for u in users:
            if u.email and u.email.endswith(".local"):
                u.email = u.email.replace(".local", ".com")
                self.db.flush()
        return users

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

    def list_distributors_for_user(self, user_id: int) -> list[int]:
        """Return list of assigned distributor IDs for a user."""
        return self.user_distributors.list_ids_for_user(user_id)

    def list_segments_for_user(self, user_id: int) -> list[str]:
        return self.user_segments.list_segments_for_user(user_id)

    def assign_distributors(
        self,
        user_id: int,
        distributor_ids: list[int],
        *,
        actor: str,
        assigned_by: Optional[int] = None,
    ) -> list[int]:
        """Assign distributors to a user (many-to-many)."""
        user = self.users.get_or_raise(user_id)
        cleaned = self.user_distributors.replace_for_user(
            user_id, distributor_ids, assigned_by=assigned_by
        )
        self._audit(
            actor=actor,
            action="Distributors Assigned",
            description=(
                f'Assigned {len(cleaned)} distributor(s) to {user.role} "{user.full_name}"'
            ),
            affected=user,
            extra_metadata={"distributor_ids": cleaned},
        )
        logger.info("Distributors updated | user_id={} | distributor_ids={}", user_id, cleaned)
        return cleaned

    def assign_segments(
        self,
        user_id: int,
        segments: list[str],
        *,
        actor: str,
        assigned_by: Optional[int] = None,
    ) -> list[str]:
        """Assign segments to a user."""
        user = self.users.get_or_raise(user_id)
        cleaned = self.user_segments.assign_segments_to_user(
            user_id, segments, assigned_by=assigned_by
        )
        self._audit(
            actor=actor,
            action="Segments Assigned",
            description=f'Assigned {len(cleaned)} segment(s) to {user.role} "{user.full_name}"',
            affected=user,
            extra_metadata={"segments": cleaned},
        )
        logger.info("Segments updated | user_id={} | segments={}", user_id, cleaned)
        return cleaned

    def get_segment_matrix(self) -> dict:
        """Return Segment Permission Matrix payload for Admin UI."""
        # Purge garbage test users from DB if present
        from sqlalchemy import update
        self.db.execute(
            update(User)
            .where(
                (User.username.ilike("matrix_user%") | User.username.ilike("anup_test%")),
                User.is_deleted.is_(False),
            )
            .values(is_deleted=True, is_active=False)
        )
        self.db.flush()

        all_segments = ["Paper", "Carpet", "Construction", "Rubber", "Gloves"]
        users = self.users.list_identity(skip=0, limit=200)
        matrix_rows = []
        for u in users:
            assigned = self.user_segments.list_segments_for_user(u.id)
            is_admin = u.role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}
            segments_map = {}
            for seg in all_segments:
                segments_map[seg] = True if is_admin else (seg in assigned)

            # Resolve associated distributors (sales owners + Admin FYIP DC links)
            assoc_distributors: list[str] = []
            assoc_distributor_ids: list[int] = []
            dist_ids = self.user_distributors.list_ids_for_user(u.id)
            if dist_ids:
                from app.models.distributor import Distributor
                from sqlalchemy import select

                dists = self.db.scalars(
                    select(Distributor).where(
                        Distributor.id.in_(dist_ids),
                        Distributor.is_deleted.is_(False),
                    )
                ).all()
                # Stable order by company name
                dists = sorted(dists, key=lambda d: (d.company or d.name or "").casefold())
                assoc_distributors = [(d.company or d.name or "").strip() for d in dists if (d.company or d.name)]
                assoc_distributor_ids = [int(d.id) for d in dists]

            matrix_rows.append(
                {
                    "id": u.id,
                    "username": u.username,
                    "fullName": u.full_name,
                    "email": u.email,
                    "role": u.role,
                    "isActive": u.is_active,
                    "segments": segments_map,
                    "assignedSegments": all_segments if is_admin else assigned,
                    "associatedDistributors": assoc_distributors,
                    "associatedDistributorIds": assoc_distributor_ids,
                }
            )
        return {
            "segments": all_segments,
            "rows": matrix_rows,
        }

    def toggle_segment_matrix_cell(
        self,
        user_id: int,
        segment: str,
        enabled: bool,
        *,
        actor: str,
        assigned_by: Optional[int] = None,
        retain_history: Optional[bool] = None,
    ) -> list[str]:
        """Toggle a single checkbox in the Segment Matrix."""
        user = self.users.get_or_raise(user_id)
        if not enabled and retain_history is None:
            from app.exceptions import ValidationAppError

            raise ValidationAppError(
                "retain_history is required when removing segment access",
                details={"user_id": user_id, "segment": segment},
            )
        updated = self.user_segments.toggle_user_segment(
            user_id,
            segment,
            enabled,
            assigned_by=assigned_by,
            retain_history=retain_history,
        )
        self._audit(
            actor=actor,
            action="Segment Matrix Updated",
            description=(
                f'Toggled segment "{segment}"={enabled} for user "{user.full_name}"'
                + (
                    f" (retain_history={retain_history})"
                    if not enabled
                    else ""
                )
            ),
            affected=user,
            extra_metadata={
                "segment": segment,
                "enabled": enabled,
                "retain_history": retain_history,
            },
        )
        return updated

    def create_user(self, payload: UserCreate, *, actor: str) -> User:
        ok, username_or_err = is_valid_username(payload.username)
        if not ok:
            raise ValidationAppError(username_or_err)
        username = username_or_err

        # Never collide with hardcoded Super Admin username
        if username == HARDCODED_SUPER_ADMIN_USERNAME:
            raise ConflictError("Username is reserved for the system Super Admin")

        if self.users.get_by_username(username):
            raise ConflictError(f"Username '{username}' is already taken")

        validate_password_strength(payload.password)

        email = (
            str(payload.email).lower()
            if payload.email
            else f"{username}@apcotex.com"
        )
        if self.users.get_by_email(email):
            raise ConflictError(f"Email {email} is already in use")

        role = payload.role.value if hasattr(payload.role, "value") else str(payload.role)
        if role == UserRole.SUPER_ADMIN.value:
            raise ForbiddenError("Cannot create a Super Admin in the database")

        if payload.outlook_sync_permission is not None:
            sync_perm = (
                payload.outlook_sync_permission.value
                if hasattr(payload.outlook_sync_permission, "value")
                else str(payload.outlook_sync_permission)
            )
        else:
            sync_perm = (
                OutlookSyncPermission.ALL.value
                if role == UserRole.ADMIN.value
                else OutlookSyncPermission.OWN.value
            )

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
            outlook_sync_permission=sync_perm,
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
            if username == HARDCODED_SUPER_ADMIN_USERNAME:
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

        if "outlook_sync_permission" in data and data["outlook_sync_permission"] is not None:
            perm = data["outlook_sync_permission"]
            data["outlook_sync_permission"] = (
                perm.value if hasattr(perm, "value") else str(perm)
            )

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

    def set_role(
        self,
        user_id: int,
        payload: RoleUpdate,
        *,
        actor: str,
        actor_role: str,
    ) -> User:
        """Promote/demote between admin and sales owner (Admin or Super Admin)."""
        user = self.users.get_or_raise(user_id)
        new_role = payload.role.value if hasattr(payload.role, "value") else str(payload.role)
        if new_role == UserRole.SUPER_ADMIN.value:
            raise ForbiddenError("Cannot assign Super Admin role to a database user")
        if user.role == new_role:
            return user

        # Only Super Admin may demote another Admin
        actor_role_norm = (actor_role or "").strip().lower()
        if (
            user.role == UserRole.ADMIN.value
            and new_role == UserRole.USER.value
            and actor_role_norm != UserRole.SUPER_ADMIN.value
        ):
            raise ForbiddenError("Only Super Admin can demote an Admin to Sales Owner")

        title = user.title
        if new_role == UserRole.ADMIN.value and not title:
            title = "Admin"
        elif new_role == UserRole.USER.value and (title or "").strip().lower() == "admin":
            title = "Sales Owner"

        sync_perm = (
            OutlookSyncPermission.ALL.value
            if new_role == UserRole.ADMIN.value
            else OutlookSyncPermission.OWN.value
        )
        updated = self.users.update(
            user, {"role": new_role, "title": title, "outlook_sync_permission": sync_perm}
        )
        verb = "Promoted to Admin" if new_role == UserRole.ADMIN.value else "Demoted to Sales Owner"
        self._audit(
            actor=actor,
            action=verb,
            description=f'{actor} changed role of "{updated.full_name}" to {new_role}',
            affected=updated,
            extra_metadata={"role": new_role},
        )
        logger.info("Role updated | user_id={} role={}", user_id, new_role)
        return updated

    def change_password(
        self,
        user_id: int,
        payload: PasswordChange,
        *,
        actor: str,
        actor_role: str = UserRole.ADMIN.value,
    ) -> User:
        user = self.users.get_or_raise(user_id)
        # Only Super Admin may change an Admin's password
        if user.role == UserRole.ADMIN.value and (actor_role or "").strip().lower() != UserRole.SUPER_ADMIN.value:
            raise ForbiddenError("Only Super Admin can change an Admin password")
        validate_password_pair(payload.new_password, payload.confirm_password)
        updated = self.users.update(user, {"password_hash": hash_password(payload.new_password)})
        self._audit(
            actor=actor,
            action="Password Reset",
            description=f'Password reset for {updated.role} "{updated.full_name}"',
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
        extra_metadata: Optional[dict] = None,
    ) -> None:
        meta = None
        if affected or extra_metadata:
            meta = {
                "affected_user": affected.full_name if affected else None,
                "affected_username": affected.username if affected else None,
                "affected_role": affected.role if affected else None,
            }
            if extra_metadata:
                meta.update(extra_metadata)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                user_role=UserRole.ADMIN.value,
                action=action,
                details=description,
                module=AuditModule.USER_MANAGEMENT.value,
                status=status,
                entity_type="user",
                entity_id=entity_id or (str(affected.id) if affected else None),
                user_id=affected.id if affected else None,
                extra_metadata=meta,
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
