"""Distributor repository."""

from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.distributor import Distributor
from app.repositories.base import BaseRepository
from app.utils.distributor_name import normalize_distributor_name


class DistributorRepository(BaseRepository[Distributor]):
    """Data access for distributors."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Distributor)

    def get_by_name(self, name: str) -> Optional[Distributor]:
        """Fetch distributor by normalized name (case-insensitive, trimmed)."""
        normalized = normalize_distributor_name(name)
        if not normalized:
            return None
        query = select(Distributor).where(
            func.lower(Distributor.name) == normalized.casefold(),
            Distributor.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def get_by_email(self, email: str) -> Optional[Distributor]:
        """Fetch distributor by email."""
        query = select(Distributor).where(
            Distributor.email == email.lower(),
            Distributor.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def get_or_create_by_name(
        self,
        name: str,
        *,
        company: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Distributor:
        """Return existing distributor by normalized name or create a new one."""
        normalized = normalize_distributor_name(name)
        if not normalized:
            raise ValueError("Distributor name is required")

        existing = self.get_by_name(normalized)
        if existing:
            updates: Dict[str, object] = {}
            # Collapse whitespace on stored name only; keep original casing
            cleaned_existing = normalize_distributor_name(existing.name)
            if cleaned_existing and cleaned_existing != existing.name:
                updates["name"] = cleaned_existing
            if company and (not existing.company or existing.company == existing.name):
                updates["company"] = company
            if address and not existing.address:
                updates["address"] = address
            if phone and not existing.phone:
                updates["phone"] = phone
            if email and not existing.email:
                updates["email"] = email.lower()
            if updates:
                return self.update(existing, updates)
            return existing
        entity = Distributor(
            name=normalized,
            company=company or normalized,
            email=email.lower() if email else None,
            address=address,
            phone=phone,
        )
        return self.create(entity)

    def as_info_map(self) -> Dict[str, Dict[str, str]]:
        """Return frontend-shaped distributor detail map keyed by name."""
        distributors = self.list(limit=5000, order_by=Distributor.name.asc())
        return {
            d.name: {
                "name": d.name,
                "company": d.company or d.name,
                "address": d.address or "",
                "phone": d.phone or "",
            }
            for d in distributors
        }

    def search(self, term: str, *, skip: int = 0, limit: int = 100) -> List[Distributor]:
        """Search distributors by name, company, or email."""
        pattern = f"%{term}%"
        query = (
            select(Distributor)
            .where(
                Distributor.is_deleted.is_(False),
                (
                    Distributor.name.ilike(pattern)
                    | Distributor.company.ilike(pattern)
                    | Distributor.email.ilike(pattern)
                ),
            )
            .order_by(Distributor.name.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(query).all())

    def count_search(self, term: str) -> int:
        """Count distributors matching a search term."""
        from sqlalchemy import func as sa_func

        pattern = f"%{term}%"
        query = select(sa_func.count()).select_from(Distributor).where(
            Distributor.is_deleted.is_(False),
            (
                Distributor.name.ilike(pattern)
                | Distributor.company.ilike(pattern)
                | Distributor.email.ilike(pattern)
            ),
        )
        return int(self.db.scalar(query) or 0)

    def list_active_ids(self) -> List[int]:
        """Return ids of all active (non-deleted) distributors."""
        query = select(Distributor.id).where(Distributor.is_deleted.is_(False))
        return list(self.db.scalars(query).all())
