"""Master data and sync job repositories."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_master import CustomerMaster
from app.models.product_master import ProductMaster
from app.models.sync_job import SyncJob
from app.repositories.base import BaseRepository


class CustomerMasterRepository(BaseRepository[CustomerMaster]):
    """Data access for customer master."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, CustomerMaster)

    def get_by_code(self, customer_code: str) -> Optional[CustomerMaster]:
        """Fetch customer by code."""
        query = select(CustomerMaster).where(
            CustomerMaster.customer_code == customer_code,
            CustomerMaster.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def upsert(
        self,
        *,
        customer_code: str,
        customer_name: str,
        segment: str,
        region: Optional[str] = None,
        country: Optional[str] = None,
        city: Optional[str] = None,
        address: Optional[str] = None,
    ) -> CustomerMaster:
        """Insert or update a customer master row."""
        existing = self.get_by_code(customer_code)
        if existing:
            return self.update(
                existing,
                {
                    "customer_name": customer_name,
                    "segment": segment,
                    "region": region,
                    "country": country,
                    "city": city,
                    "address": address,
                    "is_active": True,
                },
            )
        entity = CustomerMaster(
            customer_code=customer_code,
            customer_name=customer_name,
            segment=segment,
            region=region,
            country=country,
            city=city,
            address=address,
        )
        return self.create(entity)

    def list_names(self) -> List[str]:
        """Return active customer names for template dropdowns."""
        query = (
            select(CustomerMaster.customer_name)
            .where(CustomerMaster.is_deleted.is_(False), CustomerMaster.is_active.is_(True))
            .order_by(CustomerMaster.customer_name.asc())
        )
        return list(self.db.scalars(query).all())

    def list_segments(self) -> List[str]:
        """Return distinct segments from customer master."""
        from sqlalchemy import distinct

        query = (
            select(distinct(CustomerMaster.segment))
            .where(CustomerMaster.is_deleted.is_(False))
            .order_by(CustomerMaster.segment.asc())
        )
        return [s for s in self.db.scalars(query).all() if s]


class ProductMasterRepository(BaseRepository[ProductMaster]):
    """Data access for product master."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, ProductMaster)

    def get_by_code(self, product_code: str) -> Optional[ProductMaster]:
        """Fetch product by code."""
        query = select(ProductMaster).where(
            ProductMaster.product_code == product_code,
            ProductMaster.is_deleted.is_(False),
        )
        return self.db.scalar(query)

    def upsert(
        self,
        *,
        product_code: str,
        product_name: str,
        segment: str,
        description: Optional[str] = None,
        unit: str = "KG",
    ) -> ProductMaster:
        """Insert or update a product master row."""
        existing = self.get_by_code(product_code)
        if existing:
            return self.update(
                existing,
                {
                    "product_name": product_name,
                    "segment": segment,
                    "description": description,
                    "unit": unit,
                    "is_active": True,
                },
            )
        entity = ProductMaster(
            product_code=product_code,
            product_name=product_name,
            segment=segment,
            description=description,
            unit=unit,
        )
        return self.create(entity)

    def list_names(self) -> List[str]:
        """Return active product names for template dropdowns."""
        query = (
            select(ProductMaster.product_name)
            .where(ProductMaster.is_deleted.is_(False), ProductMaster.is_active.is_(True))
            .order_by(ProductMaster.product_name.asc())
        )
        return list(self.db.scalars(query).all())

    def list_segments(self) -> List[str]:
        """Return distinct segments from product master."""
        from sqlalchemy import distinct

        query = (
            select(distinct(ProductMaster.segment))
            .where(ProductMaster.is_deleted.is_(False))
            .order_by(ProductMaster.segment.asc())
        )
        return [s for s in self.db.scalars(query).all() if s]


class SyncJobRepository(BaseRepository[SyncJob]):
    """Data access for Outlook sync jobs."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, SyncJob)

    def get_latest(self) -> Optional[SyncJob]:
        """Return the most recent sync job."""
        query = select(SyncJob).order_by(SyncJob.started_at.desc()).limit(1)
        return self.db.scalar(query)
