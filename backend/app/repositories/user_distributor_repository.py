"""User ↔ distributor permission mapping repository."""

from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.distributor import Distributor
from app.models.user_distributor import UserDistributor
from app.repositories.base import BaseRepository
from app.utils.distributor_name import normalize_company_name, normalize_distributor_name


class UserDistributorRepository(BaseRepository[UserDistributor]):
    """Data access for user distributor assignments."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, UserDistributor)

    def list_ids_for_user(self, user_id: int) -> List[int]:
        """Return list of distributor IDs assigned to a user."""
        query = (
            select(UserDistributor.distributor_id)
            .where(UserDistributor.user_id == user_id)
            .order_by(UserDistributor.distributor_id.asc())
        )
        return list(self.db.scalars(query).all())

    def list_companies_for_user(self, user_id: int) -> List[str]:
        """Return list of distributor company/name strings assigned to a user."""
        query = (
            select(Distributor.company, Distributor.name)
            .join(UserDistributor, UserDistributor.distributor_id == Distributor.id)
            .where(
                UserDistributor.user_id == user_id,
                Distributor.is_deleted.is_(False),
            )
            .order_by(Distributor.company.asc())
        )
        rows = self.db.execute(query).all()
        result: set[str] = set()
        for company, name in rows:
            if company and company.strip():
                result.add(company.strip())
            if name and name.strip():
                result.add(name.strip())
        return sorted(list(result))

    def replace_for_user(
        self,
        user_id: int,
        distributor_ids: List[int],
        *,
        assigned_by: Optional[int] = None,
    ) -> List[int]:
        """
        Replace assigned distributors for a user with the provided list of distributor IDs.

        Returns deduplicated sorted list of assigned distributor IDs.
        """
        self.db.execute(delete(UserDistributor).where(UserDistributor.user_id == user_id))
        unique_ids = sorted(list({int(did) for did in distributor_ids if int(did) > 0}))
        for did in unique_ids:
            self.db.add(
                UserDistributor(
                    user_id=user_id,
                    distributor_id=did,
                    assigned_by=assigned_by,
                )
            )
        self.db.flush()
        return unique_ids

    def has_distributor_access(self, user_id: int, distributor: str) -> bool:
        """Return True if user is assigned to a distributor by company or name."""
        norm_company = normalize_company_name(distributor)
        norm_name = normalize_distributor_name(distributor)
        if not norm_company and not norm_name:
            return False

        query = (
            select(UserDistributor.id)
            .join(Distributor, UserDistributor.distributor_id == Distributor.id)
            .where(
                UserDistributor.user_id == user_id,
                Distributor.is_deleted.is_(False),
                (
                    (func.lower(func.trim(Distributor.company)) == norm_company.casefold())
                    | (func.lower(func.trim(Distributor.name)) == norm_name.casefold())
                ),
            )
        )
        return self.db.scalar(query) is not None
