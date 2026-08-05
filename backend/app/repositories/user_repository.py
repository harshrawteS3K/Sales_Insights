"""User repository."""

from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Data access for users."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, User)

    def get_by_email(self, email: str) -> Optional[User]:
        """Fetch active user by email."""
        query = select(User).where(User.email == email.lower(), User.is_deleted.is_(False))
        return self.db.scalar(query)

    def get_by_username(self, username: str) -> Optional[User]:
        """Fetch active (non-deleted) user by username."""
        query = select(User).where(
            User.username == username.lower(),
            User.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def list_by_role(self, role: str, *, skip: int = 0, limit: int = 100) -> List[User]:
        """List users filtered by role."""
        query = (
            select(User)
            .where(User.role == role, User.is_deleted.is_(False))
            .order_by(User.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(query).all())

    def count_by_role(self, role: str) -> int:
        """Count users filtered by role."""
        query = select(func.count()).select_from(User).where(
            User.role == role,
            User.is_deleted.is_(False),
        )
        return int(self.db.scalar(query) or 0)

    def search(self, term: str, *, skip: int = 0, limit: int = 100) -> List[User]:
        """Search users by name, email, or username."""
        return self.list_identity(skip=skip, limit=limit, search=term)

    def count_search(self, term: str) -> int:
        """Count users matching a name/email/username search."""
        return self.count_identity(search=term)

    def list_identity(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[User]:
        """List users for Super Admin identity management."""
        query = select(User).where(User.is_deleted.is_(False))
        query = self._apply_identity_filters(query, role=role, is_active=is_active, search=search)
        query = query.order_by(User.id.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(query).all())

    def count_identity(
        self,
        *,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count users for Super Admin identity management."""
        query = select(func.count()).select_from(User).where(User.is_deleted.is_(False))
        query = self._apply_identity_filters(query, role=role, is_active=is_active, search=search)
        return int(self.db.scalar(query) or 0)

    @staticmethod
    def _apply_identity_filters(query, *, role, is_active, search):
        if role:
            query = query.where(User.role == role.strip().lower())
        if is_active is not None:
            query = query.where(User.is_active.is_(is_active))
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.username.ilike(pattern),
                )
            )
        return query
