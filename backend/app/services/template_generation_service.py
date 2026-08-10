"""Official distributor template generation & download (quarterly workflow)."""

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
from app.repositories.distributor_customer_mapping_repository import (
    DistributorCustomerMappingRepository,
)
from app.repositories.distributor_repository import DistributorRepository
from app.repositories.master_repository import ProductMasterRepository
from app.repositories.sales_record_repository import SalesRecordRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.dashboard import TemplateGenerateResponse
from app.services.audit_service import AuditService
from app.services.email_package_service import EmailPackageService, sanitize_filename_part
from app.utils.files import ensure_dir
from app.utils.reporting_month import normalize_reporting_month

logger = get_logger(__name__)


class TemplateGenerationService:
    """Generate and serve the official APCOTEX quarterly distributor template."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.products = ProductMasterRepository(db)
        self.sales = SalesRecordRepository(db)
        self.distributors = DistributorRepository(db)
        self.customer_maps = DistributorCustomerMappingRepository(db)
        self.templates = ExcelTemplateGenerator()
        self.packages = EmailPackageService()
        self.audit = AuditService(db)

    def _template_path(self) -> Path:
        return Path(settings.download_dir) / DISTRIBUTOR_TEMPLATE_FILENAME

    def _version(self) -> str:
        now = datetime.now(timezone.utc)
        return f"v{now.year}.{now.month:02d}.{now.day:02d}"

    def generate(
        self,
        *,
        actor: str = "system",
        mode: str = "generic",
        distributor_id: Optional[int] = None,
        reporting_quarter: Optional[str] = None,
        output_path: Optional[Path] = None,
        update_canonical: bool = True,
    ) -> TemplateGenerateResponse:
        """
        Build quarterly template from Product Master.

        ``generic``      → Customer Name free text
        ``distributor``  → Customer Name dropdown from all historical customers
                           for the selected distributor (Reporting Quarter is
                           entered later in Excel by the distributor)
        """
        started = time.perf_counter()
        mode_key = (mode or "generic").strip().lower()
        distributor_mode = mode_key in {"distributor", "distributor_specific", "specific"}

        products_by_segment = self.products.list_codes_by_segment()
        product_count = sum(len(v) for v in products_by_segment.values())
        if not products_by_segment:
            raise ValidationAppError(
                "Cannot generate template: Product Master is empty. Upload Product Master first."
            )

        customers: list[str] = []
        contact_person: Optional[str] = None
        company_name: Optional[str] = None
        dist = None
        warning: Optional[str] = None
        fallback_generic = False
        effective_distributor_mode = distributor_mode

        # Optional prefill only (Outlook package / advanced callers). Not required.
        quarter = None
        if reporting_quarter:
            quarter = normalize_reporting_month(reporting_quarter) or reporting_quarter.strip()

        if distributor_mode:
            if not distributor_id:
                raise ValidationAppError(
                    "distributor_id is required for Distributor-Specific Template"
                )
            dist = self.distributors.get_or_raise(distributor_id)
            if not dist.is_active or dist.is_deleted:
                raise ValidationAppError("Distributor is inactive or deleted")
            customers = self.customer_maps.list_names_for_template(
                distributor_id, quarter
            )
            contact_person = (dist.contact_person or dist.name or "").strip() or None
            company_name = (dist.company or dist.name or "").strip() or None
            if not customers:
                effective_distributor_mode = False
                fallback_generic = True
                warning = (
                    "No customer history found for this distributor. "
                    "A generic template has been generated."
                )
                logger.info(
                    "Distributor template fallback to generic | distributor_id={} | quarter={}",
                    distributor_id,
                    quarter,
                )

        version = self._version()
        if distributor_mode and dist is not None:
            label = sanitize_filename_part(dist.company or dist.name)
            q_part = sanitize_filename_part(quarter or "Template")
            file_name = f"Apcotex_{label}_{q_part}_{version}.xlsx"
        else:
            file_name = f"Apcotex_Distributor_Template_{version}.xlsx"

        output = output_path or (Path(settings.download_dir) / file_name)
        ensure_dir(output.parent)

        gen_started = time.perf_counter()
        path = self.templates.generate(
            products_by_segment=products_by_segment,
            customers=customers if effective_distributor_mode else None,
            mode="distributor" if effective_distributor_mode else "generic",
            contact_person=contact_person,
            company_name=company_name,
            reporting_quarter=quarter,
            output_path=output,
        )
        gen_ms = round((time.perf_counter() - gen_started) * 1000, 2)

        if update_canonical and not distributor_mode:
            canonical = self._template_path()
            if path.resolve() != canonical.resolve():
                shutil.copyfile(path, canonical)

        generated_at = datetime.now(timezone.utc).isoformat()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        if fallback_generic:
            mode_label = "generic-fallback"
        elif effective_distributor_mode:
            mode_label = "distributor-specific"
        else:
            mode_label = "generic"
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.GENERATED,
                details=(
                    f"Generated {mode_label} quarterly template {file_name} "
                    f"({product_count:,} products, {len(customers)} customers)"
                    + (f" | {warning}" if warning else "")
                ),
                entity_type="template",
                module="Master Data",
                status="Success",
                extra_metadata={
                    "file_name": file_name,
                    "mode": mode_label,
                    "distributor_id": distributor_id,
                    "reporting_quarter": quarter,
                    "products": product_count,
                    "customers": len(customers),
                    "fallback_generic": fallback_generic,
                    "elapsed_ms": elapsed_ms,
                },
            )
        )
        logger.info(
            "Template generated | file={} mode={} products={} customers={} gen_ms={} total_ms={}",
            file_name,
            mode_label,
            product_count,
            len(customers),
            gen_ms,
            elapsed_ms,
        )
        if fallback_generic:
            message = warning or "A generic template has been generated."
        elif effective_distributor_mode:
            message = (
                "Distributor-specific template generated successfully "
                f"({len(customers)} historical customers)"
            )
        else:
            message = "Distributor template generated successfully"
        return TemplateGenerateResponse(
            success=True,
            status="ready",
            message=message,
            template_version=version,
            file_name=file_name,
            customers_count=len(customers),
            products_count=product_count,
            generated_at=generated_at,
            mode=mode_label,
            warning=warning,
            fallback_generic=fallback_generic,
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

    def generate_quarterly_package(
        self,
        *,
        distributor_id: int,
        reporting_quarter: str,
        actor: str = "system",
    ) -> tuple[Path, str]:
        """Build distributor template + Outlook .eml ZIP package."""
        dist = self.distributors.get_or_raise(distributor_id)
        if not dist.is_active or dist.is_deleted:
            raise ValidationAppError("Distributor is inactive or deleted")
        if not (dist.email or "").strip():
            raise ValidationAppError(
                "Distributor email is required to generate an Outlook draft package"
            )

        quarter = normalize_reporting_month(reporting_quarter) or reporting_quarter.strip()
        if not quarter:
            raise ValidationAppError("reporting_quarter is required (e.g. Q2 2026)")

        label = sanitize_filename_part(dist.company or dist.name)
        q_part = sanitize_filename_part(quarter)
        excel_name = f"Apcotex_{label}_{q_part}.xlsx"
        excel_path = Path(settings.download_dir) / "packages" / excel_name

        self.generate(
            actor=actor,
            mode="distributor",
            distributor_id=distributor_id,
            reporting_quarter=quarter,
            output_path=excel_path,
            update_canonical=False,
        )

        zip_path, zip_name = self.packages.write_package(
            output_dir=Path(settings.download_dir) / "packages",
            company_or_name=dist.company or dist.name,
            reporting_quarter=quarter,
            to_email=str(dist.email).strip(),
            cc_email=(dist.cc_email or None),
            contact_person=(dist.contact_person or dist.name or "Partner"),
            excel_path=excel_path,
        )

        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.GENERATED,
                details=(
                    f"Generated Outlook draft package {zip_name} for "
                    f"{dist.company or dist.name} · {quarter}"
                ),
                entity_type="distributor",
                entity_id=str(distributor_id),
                module="Distributors",
                status="Success",
                extra_metadata={
                    "zip": zip_name,
                    "reporting_quarter": quarter,
                    "distributor_id": distributor_id,
                },
            )
        )
        return zip_path, zip_name
