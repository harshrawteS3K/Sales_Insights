"""Master data and sync job repositories."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.customer_master import CustomerMaster
from app.models.product_master import ProductMaster
from app.models.sync_job import SyncJob
from app.repositories.base import BaseRepository
from app.utils.db_locks import (
    CUSTOMER_MASTER_REPLACE_LOCK,
    PRODUCT_MASTER_REPLACE_LOCK,
    acquire_xact_lock,
)

logger = get_logger(__name__)


class CustomerMasterRepository(BaseRepository[CustomerMaster]):
    """Data access for customer master."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, CustomerMaster)

    def soft_delete_all_active(self) -> int:
        """Soft-delete every active customer master row. Returns affected count."""
        now = datetime.now(timezone.utc)
        result = self.db.execute(
            update(CustomerMaster)
            .where(CustomerMaster.is_deleted.is_(False))
            .values(is_deleted=True, deleted_at=now, is_active=False)
        )
        self.db.flush()
        return int(result.rowcount or 0)

    def purge_soft_deleted_older_than(self, days: Optional[int] = None) -> int:
        """
        Hard-delete soft-deleted customer master rows older than ``days``.

        Active rows are never touched. ``days <= 0`` disables purge (returns 0).
        """
        retention = settings.master_history_retention_days if days is None else days
        if retention <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        result = self.db.execute(
            delete(CustomerMaster).where(
                CustomerMaster.is_deleted.is_(True),
                CustomerMaster.deleted_at.is_not(None),
                CustomerMaster.deleted_at < cutoff,
            )
        )
        purged = int(result.rowcount or 0)
        if purged:
            logger.info(
                "Customer master history purged | deleted={} | older_than_days={} | cutoff={}",
                purged,
                retention,
                cutoff.isoformat(),
            )
        return purged

    def replace_all(self, customer_names: Sequence[str]) -> int:
        """
        Replace the active Customer Master dataset.

        Soft-deletes previous active rows, then bulk-inserts the new set.
        Serialized via PostgreSQL advisory lock for concurrent admin safety.
        Optionally purges soft-deleted history past MASTER_HISTORY_RETENTION_DAYS.
        """
        acquire_xact_lock(self.db, CUSTOMER_MASTER_REPLACE_LOCK, label="customer_master")
        self.soft_delete_all_active()

        if not customer_names:
            self.purge_soft_deleted_older_than()
            return 0

        # bulk_insert_mappings: single multi-row INSERT, no ORM identity map overhead
        mappings = [
            {
                "customer_name": name,
                "customer_code": None,
                "segment": None,
                "is_active": True,
                "is_deleted": False,
            }
            for name in customer_names
        ]
        self.db.bulk_insert_mappings(CustomerMaster, mappings)
        self.db.flush()
        self.purge_soft_deleted_older_than()
        return len(mappings)

    def list_names(self) -> List[str]:
        """Return active customer names for template dropdowns (A–Z)."""
        query = (
            select(CustomerMaster.customer_name)
            .where(CustomerMaster.is_deleted.is_(False), CustomerMaster.is_active.is_(True))
            .order_by(CustomerMaster.customer_name.asc())
        )
        return [n for n in self.db.scalars(query).all() if n]

    def list_segments(self) -> List[str]:
        """Return distinct segments from customer master (legacy / optional)."""
        from sqlalchemy import distinct

        query = (
            select(distinct(CustomerMaster.segment))
            .where(CustomerMaster.is_deleted.is_(False), CustomerMaster.segment.is_not(None))
            .order_by(CustomerMaster.segment.asc())
        )
        return [s for s in self.db.scalars(query).all() if s]

    def get_by_code(self, customer_code: str) -> Optional[CustomerMaster]:
        """Fetch customer by legacy code."""
        query = select(CustomerMaster).where(
            CustomerMaster.customer_code == customer_code,
            CustomerMaster.is_deleted.is_(False),
        )
        return self.db.scalar(query)


class ProductMasterRepository(BaseRepository[ProductMaster]):
    """Data access for product master."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, ProductMaster)

    def soft_delete_all_active(self) -> int:
        """Soft-delete every active product master row. Returns affected count."""
        now = datetime.now(timezone.utc)
        result = self.db.execute(
            update(ProductMaster)
            .where(ProductMaster.is_deleted.is_(False))
            .values(is_deleted=True, deleted_at=now, is_active=False)
        )
        self.db.flush()
        return int(result.rowcount or 0)

    def purge_soft_deleted_older_than(self, days: Optional[int] = None) -> int:
        """
        Hard-delete soft-deleted product master rows older than ``days``.

        Active rows are never touched. ``days <= 0`` disables purge (returns 0).
        """
        retention = settings.master_history_retention_days if days is None else days
        if retention <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        result = self.db.execute(
            delete(ProductMaster).where(
                ProductMaster.is_deleted.is_(True),
                ProductMaster.deleted_at.is_not(None),
                ProductMaster.deleted_at < cutoff,
            )
        )
        purged = int(result.rowcount or 0)
        if purged:
            logger.info(
                "Product master history purged | deleted={} | older_than_days={} | cutoff={}",
                purged,
                retention,
                cutoff.isoformat(),
            )
        return purged

    def replace_all(self, products: Sequence[dict]) -> int:
        """
        Replace the active Product Master dataset.

        Each dict: industry_type, product_code, optional product_name/segment.
        Serialized via PostgreSQL advisory lock.
        Optionally purges soft-deleted history past MASTER_HISTORY_RETENTION_DAYS.
        """
        acquire_xact_lock(self.db, PRODUCT_MASTER_REPLACE_LOCK, label="product_master")
        self.soft_delete_all_active()

        if not products:
            self.purge_soft_deleted_older_than()
            return 0

        mappings = []
        for row in products:
            industry = row["industry_type"]
            code = row["product_code"]
            mappings.append(
                {
                    "industry_type": industry,
                    "product_code": code,
                    "product_name": row.get("product_name") or code,
                    "segment": row.get("segment") or industry,
                    "description": row.get("description"),
                    "unit": row.get("unit") or "KG",
                    "is_active": True,
                    "is_deleted": False,
                }
            )
        self.db.bulk_insert_mappings(ProductMaster, mappings)
        self.db.flush()
        self.purge_soft_deleted_older_than()
        return len(mappings)

    def list_product_codes(self) -> List[str]:
        """Return active product codes for template dropdowns (A–Z)."""
        query = (
            select(ProductMaster.product_code)
            .where(ProductMaster.is_deleted.is_(False), ProductMaster.is_active.is_(True))
            .order_by(ProductMaster.product_code.asc())
        )
        return [c for c in self.db.scalars(query).all() if c]

    def list_names(self) -> List[str]:
        """Return active product display names (falls back to product_code)."""
        query = (
            select(ProductMaster)
            .where(ProductMaster.is_deleted.is_(False), ProductMaster.is_active.is_(True))
            .order_by(ProductMaster.product_code.asc())
        )
        rows = list(self.db.scalars(query).all())
        return [(r.product_name or r.product_code) for r in rows]

    def list_segments(self) -> List[str]:
        """Return distinct industry/segment values from product master."""
        from sqlalchemy import distinct

        query = (
            select(distinct(ProductMaster.industry_type))
            .where(ProductMaster.is_deleted.is_(False))
            .order_by(ProductMaster.industry_type.asc())
        )
        industries = [s for s in self.db.scalars(query).all() if s]
        if industries:
            return industries
        query2 = (
            select(distinct(ProductMaster.segment))
            .where(ProductMaster.is_deleted.is_(False), ProductMaster.segment.is_not(None))
            .order_by(ProductMaster.segment.asc())
        )
        return [s for s in self.db.scalars(query2).all() if s]

    def get_by_code(self, product_code: str) -> Optional[ProductMaster]:
        """Fetch product by code."""
        query = select(ProductMaster).where(
            ProductMaster.product_code == product_code,
            ProductMaster.is_deleted.is_(False),
        )
        return self.db.scalar(query)


class SyncJobRepository(BaseRepository[SyncJob]):
    """Data access for Outlook sync jobs."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, SyncJob)

    def get_latest(self) -> Optional[SyncJob]:
        """Return the most recent sync job."""
        query = select(SyncJob).order_by(SyncJob.started_at.desc()).limit(1)
        return self.db.scalar(query)
