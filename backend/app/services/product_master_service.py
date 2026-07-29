"""Product Master upload / replace service."""

import time
from pathlib import Path
from typing import List

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction
from app.integrations.excel.parser import ExcelParserService
from app.models.product_master import ProductMaster
from app.repositories.master_repository import ProductMasterRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.dashboard import MasterDataUploadResponse
from app.services.audit_service import AuditService
from app.services.excel_validation_service import ExcelValidationService
from app.utils.files import cleanup_upload, get_upload_subdir, save_upload_file

logger = get_logger(__name__)


class ProductMasterService:
    """Upload and replace Product Master (Industry Type + Product Code)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProductMasterRepository(db)
        self.parser = ExcelParserService()
        self.validator = ExcelValidationService(self.parser)
        self.audit = AuditService(db)

    def list_products(self, *, skip: int = 0, limit: int = 500) -> List[ProductMaster]:
        return self.repo.list(skip=skip, limit=limit, order_by=ProductMaster.product_code.asc())

    def count_products(self) -> int:
        return self.repo.count()

    def fetch_product_codes(self) -> List[str]:
        return self.repo.list_product_codes()

    async def upload_and_replace(
        self,
        upload: UploadFile,
        *,
        actor: str = "system",
    ) -> MasterDataUploadResponse:
        """Validate Excel, soft-delete previous master, insert new products (transactional)."""
        started = time.perf_counter()
        self.validator.assert_excel_file(upload.filename)
        path = await save_upload_file(upload, get_upload_subdir("master"))
        success = False

        try:
            # Single workbook parse (validate + extract)
            parse_started = time.perf_counter()
            parsed = self.validator.validate_product_master_file(path)
            parse_ms = round((time.perf_counter() - parse_started) * 1000, 2)
            rows = parsed.records
            duplicates_ignored = parsed.duplicates_ignored

            tx_started = time.perf_counter()
            imported = self.repo.replace_all(rows)
            tx_ms = round((time.perf_counter() - tx_started) * 1000, 2)

            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.UPLOADED,
                    details=(
                        f"Replaced product master: {imported} imported, "
                        f"{duplicates_ignored} duplicates ignored ({elapsed_ms} ms)"
                    ),
                    entity_type="product_master",
                )
            )
            logger.info(
                "Product master replaced | imported={} duplicates={} blocks={} "
                "parse_ms={} tx_ms={} total_ms={}",
                imported,
                duplicates_ignored,
                len(parsed.blocks),
                parse_ms,
                tx_ms,
                elapsed_ms,
            )
            success = True
            return MasterDataUploadResponse(
                success=True,
                status="success",
                message=f"Product Master replaced: {imported} records imported",
                records_imported=imported,
                duplicates_ignored=duplicates_ignored,
                processing_time_ms=elapsed_ms,
                records_upserted=imported,
                records_skipped=duplicates_ignored,
                errors=[],
            )
        except Exception:
            logger.exception(
                "Product master upload failed | file={} | elapsed_ms={}",
                getattr(upload, "filename", None),
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            if success:
                cleanup_upload(path, reason="product_master_success")
            else:
                logger.info("Retaining upload for debug | file={}", Path(path).name)
