"""Distributor service."""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction
from app.exceptions import ConflictError
from app.models.distributor import Distributor
from app.repositories.distributor_repository import DistributorRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.distributor import DistributorCreate, DistributorInfo, DistributorUpdate
from app.services.audit_service import AuditService

logger = get_logger(__name__)


class DistributorService:
    """Business logic for distributors."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DistributorRepository(db)
        self.audit = AuditService(db)

    def list_distributors(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
    ) -> List[Distributor]:
        """List distributors."""
        if search:
            return self.repo.search(search, skip=skip, limit=limit)
        return self.repo.list(skip=skip, limit=limit, order_by=Distributor.name.asc())

    def count_distributors(self, *, search: Optional[str] = None) -> int:
        """Return total distributors matching the same filters as list_distributors."""
        if search:
            return self.repo.count_search(search)
        return self.repo.count()

    def get_distributor(self, distributor_id: int) -> Distributor:
        """Get distributor by id."""
        return self.repo.get_or_raise(distributor_id)

    def create_distributor(
        self,
        payload: DistributorCreate,
        *,
        actor: str = "system",
    ) -> Distributor:
        """Create a distributor."""
        if payload.email:
            existing = self.repo.get_by_email(str(payload.email).lower())
            if existing:
                raise ConflictError(f"Distributor with email {payload.email} already exists")
        entity = Distributor(
            name=payload.name,
            company=payload.company,
            address=payload.address,
            email=str(payload.email).lower() if payload.email else None,
            phone=payload.phone,
            region=payload.region,
            state=payload.state,
            city=payload.city,
            pincode=payload.pincode,
            is_active=payload.is_active,
            notes=payload.notes,
        )
        created = self.repo.create(entity)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.CREATED,
                details=f"Created distributor {created.name}",
                entity_type="distributor",
                entity_id=str(created.id),
            )
        )
        logger.info("Created distributor id={} name={}", created.id, created.name)
        return created

    def update_distributor(
        self,
        distributor_id: int,
        payload: DistributorUpdate,
        *,
        actor: str = "system",
    ) -> Distributor:
        """Update a distributor."""
        distributor = self.repo.get_or_raise(distributor_id)
        data = payload.model_dump(exclude_unset=True)
        if "email" in data and data["email"]:
            data["email"] = str(data["email"]).lower()
        updated = self.repo.update(distributor, data)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPDATED,
                details=f"Updated distributor {updated.name}",
                entity_type="distributor",
                entity_id=str(updated.id),
            )
        )
        return updated

    def delete_distributor(self, distributor_id: int, *, actor: str = "system") -> Distributor:
        """Soft-delete a distributor."""
        distributor = self.repo.get_or_raise(distributor_id)
        deleted = self.repo.soft_delete(distributor)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DELETED,
                details=f"Deleted distributor {deleted.name}",
                entity_type="distributor",
                entity_id=str(deleted.id),
            )
        )
        return deleted

    def details_map(self) -> Dict[str, DistributorInfo]:
        """Return frontend distributor detail map."""
        raw = self.repo.as_info_map()
        return {key: DistributorInfo(**value) for key, value in raw.items()}
