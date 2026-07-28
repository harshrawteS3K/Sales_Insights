"""User repository."""

from typing import List, Optional

from sqlalchemy import func, select
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
        """Search users by name or email."""
        pattern = f"%{term}%"
        query = (
            select(User)
            .where(
                User.is_deleted.is_(False),
                (User.full_name.ilike(pattern) | User.email.ilike(pattern)),
            )
            .order_by(User.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(query).all())

    def count_search(self, term: str) -> int:
        """Count users matching a name/email search."""
        pattern = f"%{term}%"
        query = select(func.count()).select_from(User).where(
            User.is_deleted.is_(False),
            (User.full_name.ilike(pattern) | User.email.ilike(pattern)),
        )
        return int(self.db.scalar(query) or 0)
