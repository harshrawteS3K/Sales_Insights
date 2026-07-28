"""Master data service for customer/product masters and template generation."""

from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.constants import DEFAULT_SEGMENTS, DISTRIBUTOR_TEMPLATE_FILENAME
from app.core.logging import get_logger
from app.enums import AuditAction
from app.integrations.excel.parser import ExcelParserService
from app.integrations.excel.template_generator import ExcelTemplateGenerator
from app.models.customer_master import CustomerMaster
from app.models.product_master import ProductMaster
from app.repositories.distributor_repository import DistributorRepository
from app.repositories.master_repository import CustomerMasterRepository, ProductMasterRepository
from app.repositories.sales_record_repository import SalesRecordRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.dashboard import MasterDataUploadResponse
from app.services.audit_service import AuditService
from app.utils.files import get_upload_subdir, save_upload_file

logger = get_logger(__name__)


class MasterDataService:
    """Business logic for master data uploads and template generation."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.customers = CustomerMasterRepository(db)
        self.products = ProductMasterRepository(db)
        self.distributors = DistributorRepository(db)
        self.sales = SalesRecordRepository(db)
        self.parser = ExcelParserService()
        self.templates = ExcelTemplateGenerator()
        self.audit = AuditService(db)

    def list_customers(self, *, skip: int = 0, limit: int = 500) -> List[CustomerMaster]:
        """List customer master rows."""
        return self.customers.list(skip=skip, limit=limit, order_by=CustomerMaster.customer_name.asc())

    def count_customers(self) -> int:
        """Return total customer master rows."""
        return self.customers.count()

    def list_products(self, *, skip: int = 0, limit: int = 500) -> List[ProductMaster]:
        """List product master rows."""
        return self.products.list(skip=skip, limit=limit, order_by=ProductMaster.product_name.asc())

    def count_products(self) -> int:
        """Return total product master rows."""
        return self.products.count()

    async def upload_customer_master(
        self,
        upload: UploadFile,
        *,
        actor: str = "system",
    ) -> MasterDataUploadResponse:
        """Upload and upsert customer master Excel."""
        path = await save_upload_file(upload, get_upload_subdir("master"))
        rows = self.parser.parse_customer_master(path)
        upserted = 0
        errors: List[str] = []
        for row in rows:
            try:
                self.customers.upsert(**row)
                upserted += 1
            except Exception as exc:
                errors.append(f"{row.get('customer_code')}: {exc}")
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPLOADED,
                details=f"Uploaded customer master ({upserted} rows)",
                entity_type="customer_master",
            )
        )
        logger.info("Customer master upload complete | upserted={} errors={}", upserted, len(errors))
        return MasterDataUploadResponse(
            success=True,
            message=f"Customer master processed: {upserted} upserted",
            records_upserted=upserted,
            records_skipped=len(errors),
            errors=errors,
        )

    async def upload_product_master(
        self,
        upload: UploadFile,
        *,
        actor: str = "system",
    ) -> MasterDataUploadResponse:
        """Upload and upsert product master Excel."""
        path = await save_upload_file(upload, get_upload_subdir("master"))
        rows = self.parser.parse_product_master(path)
        upserted = 0
        errors: List[str] = []
        for row in rows:
            try:
                self.products.upsert(**row)
                upserted += 1
            except Exception as exc:
                errors.append(f"{row.get('product_code')}: {exc}")
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPLOADED,
                details=f"Uploaded product master ({upserted} rows)",
                entity_type="product_master",
            )
        )
        logger.info("Product master upload complete | upserted={} errors={}", upserted, len(errors))
        return MasterDataUploadResponse(
            success=True,
            message=f"Product master processed: {upserted} upserted",
            records_upserted=upserted,
            records_skipped=len(errors),
            errors=errors,
        )

    def generate_distributor_template(self, *, actor: str = "system") -> Path:
        """Generate distributor Excel template with dropdowns from master data."""
        customers = self.customers.list_names()
        products = self.products.list_names()
        segments = sorted(
            set(self.customers.list_segments())
            | set(self.products.list_segments())
            | set(DEFAULT_SEGMENTS)
        )
        distributors = [d.name for d in self.distributors.list(limit=1000)]
        periods = self.sales.distinct_periods() or ["Q1 FY26", "Q2 FY26", "Q3 FY26", "Q4 FY26"]

        path = self.templates.generate(
            customers=customers,
            products=products,
            segments=segments,
            distributors=distributors,
            periods=periods,
        )
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DOWNLOADED,
                details=f"Generated distributor template {DISTRIBUTOR_TEMPLATE_FILENAME}",
                entity_type="template",
            )
        )
        return path
