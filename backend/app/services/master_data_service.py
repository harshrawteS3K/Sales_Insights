"""Master data service facade — lists + Phase 2 upload/template orchestration."""

from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.customer_master import CustomerMaster
from app.models.product_master import ProductMaster
from app.schemas.dashboard import MasterDataUploadResponse, TemplateGenerateResponse
from app.schemas.distributor import TemplateGenerateRequest
from app.services.customer_master_service import CustomerMasterService
from app.services.product_master_service import ProductMasterService
from app.services.template_generation_service import TemplateGenerationService


class MasterDataService:
    """
    Facade over CustomerMasterService, ProductMasterService, TemplateGenerationService.

    Keeps existing DI / endpoint wiring stable while Phase 2 logic lives in modular services.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.customer_service = CustomerMasterService(db)
        self.product_service = ProductMasterService(db)
        self.template_service = TemplateGenerationService(db)

    def list_customers(self, *, skip: int = 0, limit: int = 500) -> List[CustomerMaster]:
        return self.customer_service.list_customers(skip=skip, limit=limit)

    def count_customers(self) -> int:
        return self.customer_service.count_customers()

    def list_products(self, *, skip: int = 0, limit: int = 500) -> List[ProductMaster]:
        return self.product_service.list_products(skip=skip, limit=limit)

    def count_products(self) -> int:
        return self.product_service.count_products()

    async def upload_customer_master(
        self,
        upload: UploadFile,
        *,
        actor: str = "system",
    ) -> MasterDataUploadResponse:
        return await self.customer_service.upload_and_replace(upload, actor=actor)

    async def upload_product_master(
        self,
        upload: UploadFile,
        *,
        actor: str = "system",
    ) -> MasterDataUploadResponse:
        return await self.product_service.upload_and_replace(upload, actor=actor)

    def generate_distributor_template(self, *, actor: str = "system") -> Path:
        """Generate template and return filesystem path (legacy helper)."""
        result = self.template_service.generate(actor=actor)
        path, _ = self.template_service.resolve_download_path(preferred_name=result.file_name)
        return path

    def generate_template(
        self,
        *,
        actor: str = "system",
        request: Optional[TemplateGenerateRequest] = None,
    ) -> TemplateGenerateResponse:
        req = request or TemplateGenerateRequest()
        return self.template_service.generate(
            actor=actor,
            mode=req.mode,
            distributor_id=req.distributor_id,
            reporting_quarter=req.reporting_quarter,
        )

    def generate_quarterly_package(
        self,
        *,
        distributor_id: int,
        reporting_quarter: str,
        actor: str = "system",
    ):
        """Create Microsoft Graph Outlook draft with distributor-specific Excel."""
        return self.template_service.create_email_draft(
            distributor_id=distributor_id,
            reporting_quarter=reporting_quarter,
            actor=actor,
        )

    def create_email_draft(
        self,
        *,
        distributor_id: int,
        reporting_quarter: str,
        actor: str = "system",
    ):
        return self.template_service.create_email_draft(
            distributor_id=distributor_id,
            reporting_quarter=reporting_quarter,
            actor=actor,
        )

    def resolve_template_download(self, *, preferred_name: str | None = None) -> tuple[Path, str]:
        return self.template_service.resolve_download_path(preferred_name=preferred_name)
