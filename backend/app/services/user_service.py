"""User service."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction
from app.exceptions import ConflictError
from app.models.user import User
from app.repositories.audit_repository import AuditTrailRepository
from app.repositories.user_repository import UserRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import AuditService

logger = get_logger(__name__)


class UserService:
    """Business logic for user management."""

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
        search: Optional[str] = None,
    ) -> List[User]:
        """List users with optional filters."""
        if search:
            return self.users.search(search, skip=skip, limit=limit)
        if role:
            return self.users.list_by_role(role, skip=skip, limit=limit)
        return self.users.list(skip=skip, limit=limit, order_by=User.id.desc())

    def count_users(
        self,
        *,
        role: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Return total users matching the same filters as list_users."""
        if search:
            return self.users.count_search(search)
        if role:
            return self.users.count_by_role(role)
        return self.users.count()

    def get_user(self, user_id: int) -> User:
        """Get user by id."""
        return self.users.get_or_raise(user_id)

    def create_user(self, payload: UserCreate, *, actor: str = "system") -> User:
        """Create a new user."""
        existing = self.users.get_by_email(str(payload.email).lower())
        if existing:
            raise ConflictError(f"User with email {payload.email} already exists")
        entity = User(
            email=str(payload.email).lower(),
            full_name=payload.full_name,
            title=payload.title,
            role=payload.role.value if hasattr(payload.role, "value") else str(payload.role),
            phone=payload.phone,
            department=payload.department,
            notes=payload.notes,
            is_active=payload.is_active,
        )
        created = self.users.create(entity)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.CREATED,
                details=f"Created user {created.email}",
                entity_type="user",
                entity_id=str(created.id),
            )
        )
        logger.info("Created user id={} email={}", created.id, created.email)
        return created

    def update_user(self, user_id: int, payload: UserUpdate, *, actor: str = "system") -> User:
        """Update an existing user."""
        user = self.users.get_or_raise(user_id)
        data = payload.model_dump(exclude_unset=True)
        if "email" in data and data["email"]:
            data["email"] = str(data["email"]).lower()
            conflict = self.users.get_by_email(data["email"])
            if conflict and conflict.id != user_id:
                raise ConflictError(f"User with email {data['email']} already exists")
        if "role" in data and data["role"] is not None:
            role = data["role"]
            data["role"] = role.value if hasattr(role, "value") else str(role)
        updated = self.users.update(user, data)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPDATED,
                details=f"Updated user {updated.email}",
                entity_type="user",
                entity_id=str(updated.id),
            )
        )
        return updated

    def delete_user(self, user_id: int, *, actor: str = "system") -> User:
        """Soft-delete a user."""
        user = self.users.get_or_raise(user_id)
        deleted = self.users.soft_delete(user)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DELETED,
                details=f"Deleted user {deleted.email}",
                entity_type="user",
                entity_id=str(deleted.id),
            )
        )
        return deleted
