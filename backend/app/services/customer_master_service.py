"""Customer Master upload / replace service."""

import time
from pathlib import Path
from typing import List

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction
from app.integrations.excel.parser import ExcelParserService
from app.models.customer_master import CustomerMaster
from app.repositories.master_repository import CustomerMasterRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.dashboard import MasterDataUploadResponse
from app.services.audit_service import AuditService
from app.services.excel_validation_service import ExcelValidationService
from app.utils.files import cleanup_upload, get_upload_subdir, save_upload_file

logger = get_logger(__name__)


class CustomerMasterService:
    """Upload and replace Customer Master (CUSTOMER NAME)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CustomerMasterRepository(db)
        self.parser = ExcelParserService()
        self.validator = ExcelValidationService(self.parser)
        self.audit = AuditService(db)

    def list_customers(self, *, skip: int = 0, limit: int = 500) -> List[CustomerMaster]:
        return self.repo.list(skip=skip, limit=limit, order_by=CustomerMaster.customer_name.asc())

    def count_customers(self) -> int:
        return self.repo.count()

    def fetch_names(self) -> List[str]:
        return self.repo.list_names()

    async def upload_and_replace(
        self,
        upload: UploadFile,
        *,
        actor: str = "system",
    ) -> MasterDataUploadResponse:
        """Validate Excel, soft-delete previous master, insert new names (transactional)."""
        started = time.perf_counter()
        self.validator.assert_excel_file(upload.filename)
        path = await save_upload_file(upload, get_upload_subdir("master"))
        success = False

        try:
            # Single pass: parse validates headers then extracts rows
            parse_started = time.perf_counter()
            rows, duplicates_ignored = self.parser.parse_customer_master(path)
            parse_ms = round((time.perf_counter() - parse_started) * 1000, 2)
            names = [r["customer_name"] for r in rows]

            tx_started = time.perf_counter()
            imported = self.repo.replace_all(names)
            tx_ms = round((time.perf_counter() - tx_started) * 1000, 2)

            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.UPLOADED,
                    details=(
                        f"Replaced customer master: {imported} imported, "
                        f"{duplicates_ignored} duplicates ignored ({elapsed_ms} ms)"
                    ),
                    entity_type="customer_master",
                )
            )
            logger.info(
                "Customer master replaced | imported={} duplicates={} "
                "parse_ms={} tx_ms={} total_ms={}",
                imported,
                duplicates_ignored,
                parse_ms,
                tx_ms,
                elapsed_ms,
            )
            success = True
            return MasterDataUploadResponse(
                success=True,
                status="success",
                message=f"Customer Master replaced: {imported} records imported",
                records_imported=imported,
                duplicates_ignored=duplicates_ignored,
                processing_time_ms=elapsed_ms,
                records_upserted=imported,
                records_skipped=duplicates_ignored,
                errors=[],
            )
        except Exception:
            logger.exception(
                "Customer master upload failed | file={} | elapsed_ms={}",
                getattr(upload, "filename", None),
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            if success:
                cleanup_upload(path, reason="customer_master_success")
            else:
                logger.info("Retaining upload for debug | file={}", Path(path).name)
