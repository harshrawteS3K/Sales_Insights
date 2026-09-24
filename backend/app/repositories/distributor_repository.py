"""Distributor repository — company is the business identity."""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.distributor import Distributor
from app.repositories.base import BaseRepository
from app.utils.distributor_name import normalize_company_name, normalize_distributor_name


class DistributorRepository(BaseRepository[Distributor]):
    """Data access for distributors (one row per Distributor Company)."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Distributor)

    def _active_distributors(self) -> List[Distributor]:
        query = (
            select(Distributor)
            .where(Distributor.is_deleted.is_(False))
            .order_by(Distributor.id.asc())
        )
        return list(self.db.scalars(query).all())

    def _find_by_match_key(self, raw: str) -> Optional[Distributor]:
        """Resolve S.K.TRADING / SK Trading / S.K.TRADING COMPANY to one row."""
        key = normalize_distributor_name(raw)
        if not key:
            return None
        for row in self._active_distributors():
            if normalize_distributor_name(row.company) == key or normalize_distributor_name(row.name) == key:
                return row
        return None

    def get_by_name(self, name: str) -> Optional[Distributor]:
        """Fetch distributor by representative name (legacy / metadata lookup)."""
        return self._find_by_match_key(name)

    def get_by_company(self, company: str) -> Optional[Distributor]:
        """Fetch distributor by normalized company name (business identity)."""
        return self._find_by_match_key(company)

    def list_ids_for_company(self, company: str) -> List[int]:
        """All active distributor ids sharing the same company (incl. legacy dupes)."""
        key = normalize_distributor_name(company)
        if not key:
            return []
        return [
            row.id
            for row in self._active_distributors()
            if normalize_distributor_name(row.company) == key or normalize_distributor_name(row.name) == key
        ]

    def get_by_email(self, email: str) -> Optional[Distributor]:
        """Fetch distributor by email."""
        query = select(Distributor).where(
            Distributor.email == email.lower(),
            Distributor.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def get_or_create_by_company(
        self,
        company: str,
        *,
        representative_name: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Distributor:
        """
        Return the distributor row for this company, or create one.

        Business identity = Distributor Company.
        ``name`` stores the latest known representative (metadata only).
        """
        company_norm = normalize_company_name(company)
        rep_norm = normalize_company_name(representative_name)
        if not company_norm:
            # Legacy Excel without Company Name → use representative as company key
            company_norm = rep_norm
        if not company_norm:
            raise ValueError("Distributor Company is required")

        existing = self.get_by_company(company_norm)
        if existing is None and rep_norm:
            existing = self.get_by_name(rep_norm)
        if existing:
            updates: Dict[str, object] = {}
            cleaned_company = normalize_company_name(existing.company)
            if cleaned_company and cleaned_company != existing.company:
                updates["company"] = cleaned_company
            # Keep the stored name when punctuation/suffix variants are the same company.
            if (
                rep_norm
                and normalize_distributor_name(existing.name) != normalize_distributor_name(rep_norm)
                and existing.name.casefold() != rep_norm.casefold()
            ):
                updates["name"] = rep_norm
            else:
                cleaned_existing_name = normalize_company_name(existing.name)
                if cleaned_existing_name and cleaned_existing_name != existing.name:
                    updates["name"] = cleaned_existing_name
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
            name=rep_norm or company_norm,
            company=company_norm,
            email=email.lower() if email else None,
            address=address,
            phone=phone,
        )
        return self.create(entity)

    def get_or_create_by_name(
        self,
        name: str,
        *,
        company: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Distributor:
        """
        Compatibility wrapper — resolves by company when provided.

        Prefer ``get_or_create_by_company`` for new call sites.
        """
        company_key = normalize_company_name(company) or normalize_company_name(name)
        return self.get_or_create_by_company(
            company_key,
            representative_name=name,
            email=email,
            address=address,
            phone=phone,
        )

    def as_info_map(self) -> Dict[str, Dict[str, str]]:
        """Return frontend-shaped distributor detail map keyed by company."""
        distributors = self.list(limit=5000, order_by=Distributor.company.asc())
        result: Dict[str, Dict[str, str]] = {}
        for d in distributors:
            key = d.company or d.name
            result[key] = {
                "name": d.name,
                "company": d.company or d.name,
                "address": d.address or "",
                "phone": d.phone or "",
            }
            # Also key by representative for legacy clients
            if d.name and d.name not in result:
                result[d.name] = result[key]
        return result

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
                    | Distributor.region.ilike(pattern)
                ),
            )
            .order_by(Distributor.company.asc())
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
                | Distributor.region.ilike(pattern)
            ),
        )
        return int(self.db.scalar(query) or 0)

    def list_active_ids(self) -> List[int]:
        """Return ids of all active (non-deleted) distributors."""
        query = select(Distributor.id).where(Distributor.is_deleted.is_(False))
        return list(self.db.scalars(query).all())
