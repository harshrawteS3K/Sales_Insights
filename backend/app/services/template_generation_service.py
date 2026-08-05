"""Official distributor template generation & download."""

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.constants import DISTRIBUTOR_TEMPLATE_FILENAME
from app.core.config import settings
from app.core.logging import get_logger
from app.enums import AuditAction
from app.exceptions import ValidationAppError
from app.integrations.excel.template_generator import ExcelTemplateGenerator
from app.repositories.master_repository import CustomerMasterRepository, ProductMasterRepository
from app.repositories.sales_record_repository import SalesRecordRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.dashboard import TemplateGenerateResponse
from app.services.audit_service import AuditService
from app.utils.files import ensure_dir

logger = get_logger(__name__)


class TemplateGenerationService:
    """Generate and serve the official APCOTEX distributor template."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.customers = CustomerMasterRepository(db)
        self.products = ProductMasterRepository(db)
        self.sales = SalesRecordRepository(db)
        self.templates = ExcelTemplateGenerator()
        self.audit = AuditService(db)

    def _template_path(self) -> Path:
        return Path(settings.download_dir) / DISTRIBUTOR_TEMPLATE_FILENAME

    def _version(self) -> str:
        now = datetime.now(timezone.utc)
        return f"v{now.year}.{now.month:02d}.{now.day:02d}"

    def generate(self, *, actor: str = "system") -> TemplateGenerateResponse:
        """
        Build template from active master data.

        Customer dropdown ← customer_master.customer_name (A–Z, unique, active)
        Segment dropdown  ← product_master.industry_type (unique, A–Z)
        Product dropdown  ← product codes for the selected Segment only
        """
        started = time.perf_counter()
        customer_names = self.customers.list_names()
        products_by_segment = self.products.list_codes_by_segment()
        product_count = sum(len(v) for v in products_by_segment.values())

        if not customer_names:
            raise ValidationAppError(
                "Cannot generate template: Customer Master is empty. Upload Customer Master first."
            )
        if not products_by_segment:
            raise ValidationAppError(
                "Cannot generate template: Product Master is empty. Upload Product Master first."
            )

        # Reporting Month dropdown options only — never prefill distributor header fields
        periods = self.sales.distinct_periods() or None

        version = self._version()
        file_name = f"Apcotex_Distributor_Template_{version}.xlsx"
        output = Path(settings.download_dir) / file_name
        ensure_dir(output.parent)

        gen_started = time.perf_counter()
        path = self.templates.generate(
            customers=customer_names,
            products_by_segment=products_by_segment,
            periods=periods,
            output_path=output,
        )
        gen_ms = round((time.perf_counter() - gen_started) * 1000, 2)

        # Canonical download alias (copyfile avoids loading whole workbook into RAM)
        canonical = self._template_path()
        if path.resolve() != canonical.resolve():
            shutil.copyfile(path, canonical)

        generated_at = datetime.now(timezone.utc).isoformat()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.GENERATED,
                details=(
                    f"Generated distributor template {file_name} "
                    f"using Customer Master ({len(customer_names):,} customers) and "
                    f"Product Master ({product_count:,} products across "
                    f"{len(products_by_segment)} segments)"
                ),
                entity_type="template",
                module="Master Data",
                status="Success",
                extra_metadata={
                    "file_name": file_name,
                    "customers": len(customer_names),
                    "products": product_count,
                    "segments": len(products_by_segment),
                    "elapsed_ms": elapsed_ms,
                },
            )
        )
        logger.info(
            "Template generated | file={} customers={} products={} segments={} gen_ms={} total_ms={}",
            file_name,
            len(customer_names),
            product_count,
            len(products_by_segment),
            gen_ms,
            elapsed_ms,
        )
        return TemplateGenerateResponse(
            success=True,
            status="ready",
            message="Distributor template generated successfully",
            template_version=version,
            file_name=file_name,
            customers_count=len(customer_names),
            products_count=product_count,
            generated_at=generated_at,
        )

    def resolve_download_path(self, *, preferred_name: Optional[str] = None) -> tuple[Path, str]:
        """Return (path, download_filename) for the latest generated template."""
        download_dir = Path(settings.download_dir)
        if preferred_name:
            candidate = download_dir / preferred_name
            if candidate.is_file():
                return candidate, preferred_name

        matches = sorted(
            download_dir.glob("Apcotex_Distributor_Template_*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0], matches[0].name

        canonical = self._template_path()
        if canonical.is_file():
            return canonical, DISTRIBUTOR_TEMPLATE_FILENAME

        raise ValidationAppError(
            "No generated template found. Call POST /template/generate first."
        )
