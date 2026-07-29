"""Generic base repository with shared CRUD operations."""

from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.base import Base
from app.exceptions import NotFoundError

ModelT = TypeVar("ModelT", bound=Base)
logger = get_logger(__name__)


class BaseRepository(Generic[ModelT]):
    """Reusable repository base for SQLAlchemy models."""

    def __init__(self, db: Session, model: Type[ModelT]) -> None:
        self.db = db
        self.model = model

    def get_by_id(self, entity_id: int, *, include_deleted: bool = False) -> Optional[ModelT]:
        """Fetch a single entity by primary key."""
        query = select(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        if hasattr(self.model, "is_deleted") and not include_deleted:
            query = query.where(self.model.is_deleted.is_(False))  # type: ignore[attr-defined]
        return self.db.scalar(query)

    def get_or_raise(self, entity_id: int, *, include_deleted: bool = False) -> ModelT:
        """Fetch entity or raise NotFoundError."""
        entity = self.get_by_id(entity_id, include_deleted=include_deleted)
        if entity is None:
            raise NotFoundError(f"{self.model.__name__} with id={entity_id} not found")
        return entity

    def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
        order_by: Any = None,
    ) -> List[ModelT]:
        """Return a paginated list of entities."""
        query: Select[Any] = select(self.model)
        if hasattr(self.model, "is_deleted") and not include_deleted:
            query = query.where(self.model.is_deleted.is_(False))  # type: ignore[attr-defined]
        if order_by is not None:
            query = query.order_by(order_by)
        else:
            query = query.order_by(self.model.id.desc())  # type: ignore[attr-defined]
        query = query.offset(skip).limit(limit)
        return list(self.db.scalars(query).all())

    def count(self, *, include_deleted: bool = False) -> int:
        """Return total count of entities."""
        query = select(func.count()).select_from(self.model)
        if hasattr(self.model, "is_deleted") and not include_deleted:
            query = query.where(self.model.is_deleted.is_(False))  # type: ignore[attr-defined]
        return int(self.db.scalar(query) or 0)

    def create(self, entity: ModelT) -> ModelT:
        """Persist a new entity."""
        self.db.add(entity)
        self.db.flush()
        self.db.refresh(entity)
        logger.debug("Created {} id={}", self.model.__name__, getattr(entity, "id", None))
        return entity

    def create_many(self, entities: List[ModelT]) -> List[ModelT]:
        """
        Persist multiple entities efficiently.

        Uses a single flush — no per-row refresh (avoids N SELECT round-trips).
        Primary keys are populated on flush via INSERT … RETURNING (PostgreSQL).
        """
        if not entities:
            return entities
        self.db.add_all(entities)
        self.db.flush()
        logger.debug("Created {} {} rows (bulk)", len(entities), self.model.__name__)
        return entities

    def update(self, entity: ModelT, data: Dict[str, Any]) -> ModelT:
        """Update entity fields from a dict (allows explicit None to clear nullables)."""
        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        self.db.flush()
        self.db.refresh(entity)
        logger.debug("Updated {} id={}", self.model.__name__, getattr(entity, "id", None))
        return entity

    def soft_delete(self, entity: ModelT) -> ModelT:
        """Soft-delete an entity when supported."""
        if not hasattr(entity, "is_deleted"):
            raise AttributeError(f"{self.model.__name__} does not support soft delete")
        entity.is_deleted = True  # type: ignore[attr-defined]
        if hasattr(entity, "deleted_at"):
            entity.deleted_at = datetime.now(timezone.utc)  # type: ignore[attr-defined]
        self.db.flush()
        self.db.refresh(entity)
        logger.debug("Soft-deleted {} id={}", self.model.__name__, getattr(entity, "id", None))
        return entity

    def hard_delete(self, entity: ModelT) -> None:
        """Permanently delete an entity."""
        self.db.delete(entity)
        self.db.flush()
        logger.debug("Hard-deleted {}", self.model.__name__)
