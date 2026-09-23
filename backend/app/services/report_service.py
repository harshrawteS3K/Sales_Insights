"""Report and sales ingestion service."""

from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction, ReportSource, ReportStatus
from app.exceptions import ConflictError, ExcelProcessingError, ValidationAppError
from app.erp_parser import ERPParserService, ERPParseResult
from app.integrations.excel.mapper import SalesRecordMapper
from app.models.report import Report
from app.repositories.distributor_repository import DistributorRepository
from app.repositories.email_repository import EmailMessageRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.sales_record_repository import SalesRecordRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.report import FrontendReport, ReportCategories, ReportCreate, ReportUpdate
from app.schemas.sales_record import FrontendSalesRecord, ParsedSalesRow
from app.services.audit_service import AuditService
from app.utils.datetime_utils import format_report_date, utc_now
from app.utils.db_locks import acquire_report_replace_lock
from app.utils.files import get_upload_subdir, save_upload_file
from app.utils.hashing import sha256_file, sha256_bytes, build_sales_row_hash
from app.utils.quantity import format_quantity
from app.utils.reporting_month import months_equivalent, normalize_reporting_month
from app.utils.validation_summary import build_validation_summary

logger = get_logger(__name__)

DUPLICATE_SUBMISSION_MESSAGE = (
    "Duplicate submission detected. This sales data already exists for the "
    "selected Financial Year and Quarter."
)


class ReportService:
    """Business logic for reports and sales Excel ingestion."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.reports = ReportRepository(db)
        self.sales = SalesRecordRepository(db)
        self.distributors = DistributorRepository(db)
        self.emails = EmailMessageRepository(db)
        self.parser = ERPParserService()
        self.audit = AuditService(db)

    def list_reports(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        source: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> List[Report]:
        """List reports with filters."""
        return self.reports.list_with_filters(
            status=status,
            source=source,
            report_type=report_type,
            skip=skip,
            limit=limit,
        )

    def count_reports(
        self,
        *,
        status: Optional[str] = None,
        source: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> int:
        """Return total reports matching the same filters as list_reports."""
        return self.reports.count_with_filters(
            status=status,
            source=source,
            report_type=report_type,
        )

    def get_report(self, report_id: int) -> Report:
        """Get report by id."""
        return self.reports.get_or_raise(report_id)

    def create_report(self, payload: ReportCreate, *, actor: str = "system") -> Report:
        """Create a manual report metadata row (ghost reports blocked; one-active rule)."""
        if payload.distributor_id is None:
            raise ValidationAppError(
                "distributor_id is required — refusing to create a ghost report without a Distributor"
            )
        reporting_month = normalize_reporting_month(payload.reporting_month or "")
        if not reporting_month:
            raise ValidationAppError(
                "reporting_month is required — refusing to create a ghost report without a Reporting Quarter"
            )
        distributor = self.distributors.get_or_raise(payload.distributor_id)
        company = distributor.company or distributor.name

        # Enforce one active report per Distributor Company + Reporting Month
        acquire_report_replace_lock(
            self.db, payload.distributor_id, reporting_month, company=company
        )
        self._retire_matching_active_reports(
            distributor_id=payload.distributor_id,
            reporting_month=reporting_month,
            distributor_name=company,
            actor=actor,
            company=company,
        )

        entity = Report(
            name=payload.name,
            description=payload.description,
            report_type=payload.report_type,
            reporting_month=reporting_month,
            categories=payload.categories.model_dump() if payload.categories else None,
            distributor_id=payload.distributor_id,
            source=payload.source.value,
            status=payload.status.value,
            report_date=utc_now(),
            uploaded_by=None,
        )
        created = self.reports.create(entity)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.CREATED,
                details=(
                    f"Created report {created.name} | distributor={distributor.name} | "
                    f"reporting_month={reporting_month}"
                ),
                report_name=created.name,
                entity_type="report",
                entity_id=str(created.id),
            )
        )
        return created

    def update_report(
        self,
        report_id: int,
        payload: ReportUpdate,
        *,
        actor: str = "system",
    ) -> Report:
        """Update report metadata (preserves one-active business key)."""
        report = self.reports.get_or_raise(report_id)
        data = payload.model_dump(exclude_unset=True)
        if "categories" in data and data["categories"] is not None:
            cats = data["categories"]
            data["categories"] = cats if isinstance(cats, dict) else cats
        if "status" in data and data["status"] is not None:
            status = data["status"]
            data["status"] = status.value if hasattr(status, "value") else status

        if "reporting_month" in data and data["reporting_month"] is not None:
            data["reporting_month"] = normalize_reporting_month(data["reporting_month"])

        new_distributor_id = data.get("distributor_id", report.distributor_id)
        new_month = data.get("reporting_month", report.reporting_month)
        key_changed = (
            new_distributor_id != report.distributor_id
            or normalize_reporting_month(new_month or "")
            != normalize_reporting_month(report.reporting_month or "")
        )
        if key_changed and new_distributor_id and new_month:
            distributor = self.distributors.get_or_raise(int(new_distributor_id))
            company = distributor.company or distributor.name
            acquire_report_replace_lock(
                self.db, int(new_distributor_id), str(new_month), company=company
            )
            for existing in self.reports.list_active_for_company(company):
                if existing.id == report.id:
                    continue
                if months_equivalent(existing.reporting_month, new_month):
                    self._retire_active_report(
                        existing,
                        actor=actor,
                        distributor_name=company,
                        reporting_month=normalize_reporting_month(new_month),
                        reason="Report Replacement (metadata update)",
                    )

        updated = self.reports.update(report, data)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPDATED,
                details=f"Updated report {updated.name}",
                report_name=updated.name,
                entity_type="report",
                entity_id=str(updated.id),
            )
        )
        return updated

    def delete_report(self, report_id: int, *, actor: str = "system") -> Report:
        """Soft-delete a report and all associated sales records (audit retained)."""
        report = self.reports.get_or_raise(report_id)
        sales_deleted = self.sales.soft_delete_for_report(report.id)
        deleted = self.reports.soft_delete(report)
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DELETED,
                details=(
                    f"Deleted report {deleted.name} | distributor_id={deleted.distributor_id} | "
                    f"reporting_month={deleted.reporting_month} | sales_soft_deleted={sales_deleted}"
                ),
                report_name=deleted.name,
                entity_type="report",
                entity_id=str(deleted.id),
            )
        )
        return deleted

    def _resolve_business_identity(
        self,
        parsed_rows: List[ParsedSalesRow],
        parse_result: ERPParseResult,
        *,
        reporting_quarter: Optional[str] = None,
        distributor_company: Optional[str] = None,
        distributor_id: Optional[int] = None,
        email_message_id: Optional[int] = None,
    ) -> Tuple[str, str, str, int, dict[str, int]]:
        """
        Resolve Distributor Company + Reporting Quarter.

        Distributor and quarter come from the email/UI flow — never from Excel.
        """
        if not parsed_rows or parse_result.imported_rows <= 0:
            raise ValidationAppError(
                "No sales records to import — refusing to create an empty report",
                details={
                    "expected_rows": parse_result.expected_rows,
                    "imported_rows": parse_result.imported_rows,
                    "quality_score": parse_result.quality_score,
                    "sheet": parse_result.sheet_name,
                    "errors": parse_result.row_errors,
                },
            )

        reporting_month = normalize_reporting_month(
            (reporting_quarter or "").strip()
            or (parse_result.reporting_month or "").strip()
            or "Q1 2024-25"
        )

        company_key = (distributor_company or "").strip()
        representative = ""

        if distributor_id is not None:
            dist = self.distributors.get_or_raise(distributor_id)
            company_key = (dist.company or dist.name or company_key).strip()
            representative = (dist.contact_person or dist.name or "").strip()
        elif company_key:
            dist = self.distributors.get_or_create_by_company(
                company_key,
                representative_name=company_key,
            )
            representative = (dist.contact_person or dist.name or company_key).strip()
        elif email_message_id:
            email_msg = self.emails.get_by_id(email_message_id)
            if email_msg is None:
                raise ValidationAppError("Email message not found for distributor resolution")
            sender_email = (email_msg.sender_email or "").strip()
            sender_name = (email_msg.sender_name or "").strip()
            dist = None
            if sender_email:
                dist = self.distributors.get_by_email(sender_email)
            if dist is None:
                # Fall back: treat sender display name / local-part as company key
                fallback = sender_name or (sender_email.split("@")[0] if sender_email else "")
                if not fallback:
                    raise ValidationAppError(
                        "Distributor could not be resolved from email sender. "
                        "Map the sender email to a distributor or select a distributor."
                    )
                dist = self.distributors.get_or_create_by_company(
                    fallback,
                    representative_name=sender_name or fallback,
                )
                if sender_email and not (dist.email or "").strip():
                    dist.email = sender_email
                    self.db.flush()
            company_key = (dist.company or dist.name or "").strip()
            representative = (dist.contact_person or dist.name or sender_name or "").strip()
        else:
            fallback_name = None
            if parse_result.distributor_details and parse_result.distributor_details.get("company"):
                fallback_name = parse_result.distributor_details["company"]
            elif parsed_rows and parsed_rows[0].distributor:
                fallback_name = parsed_rows[0].distributor
            
            fallback_name = fallback_name or "Default Distributor"
            dist = self.distributors.get_or_create_by_company(
                fallback_name,
                representative_name=fallback_name,
            )
            company_key = (dist.company or dist.name or fallback_name).strip()
            representative = (dist.contact_person or dist.name or fallback_name).strip()

        if parse_result.quality_score is None:
            raise ValidationAppError(
                "Confidence score was not calculated — refusing to create a report",
            )

        distributor = self.distributors.get_or_create_by_company(
            company_key,
            representative_name=representative or company_key,
        )
        label = representative or company_key
        distributor_ids: dict[str, int] = {label: distributor.id, company_key: distributor.id}
        from app.utils.hashing import build_sales_row_hash

        for row in parsed_rows:
            row.distributor = label
            row.company = distributor.company or company_key
            row.period = reporting_month
            row.segment = row.segment or ""
            row.row_hash = build_sales_row_hash(
                label,
                row.customer_name,
                row.segment,
                row.product,
                row.quantity,
                reporting_month,
            )

        return (
            distributor.company or company_key,
            representative or company_key,
            reporting_month,
            distributor.id,
            distributor_ids,
        )

    def _retire_active_report(
        self,
        existing: Report,
        *,
        actor: str,
        distributor_name: str,
        reporting_month: str,
        reason: str = "Report Replacement",
    ) -> int:
        """Soft-delete an active report and all its sales. Returns sales count retired."""
        sales_deleted = self.sales.soft_delete_for_report(existing.id)
        self.reports.soft_delete(existing)
        self.db.flush()
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.REPLACED,
                details=(
                    f"{reason} | soft-deleted previous report id={existing.id} | "
                    f"distributor={distributor_name} | reporting_month={reporting_month} | "
                    f"sales_soft_deleted={sales_deleted} | sender={existing.sender_email}"
                ),
                report_name=existing.name,
                entity_type="report",
                entity_id=str(existing.id),
            )
        )
        logger.info(
            "Business report retired | previous_id={} | distributor={} | reporting_month={} | sales={}",
            existing.id,
            distributor_name,
            reporting_month,
            sales_deleted,
        )
        return sales_deleted

    @staticmethod
    def _normalize_report_file_key(file_name: Optional[str]) -> str:
        """Strip attachment hash prefix so re-uploads of the same Excel match."""
        import re

        name = Path(file_name or "").name.strip()
        # uploads often look like ``{32hex}_{original.xlsx}``
        return re.sub(r"^[0-9a-f]{32}_", "", name, flags=re.IGNORECASE).casefold()

    def _aggregate_parsed_rows(
        self,
        rows: List[ParsedSalesRow],
        *,
        company: str,
        reporting_month: str,
    ) -> List[ParsedSalesRow]:
        """Sum duplicate Customer×Product×Period lines so row_hash stays unique."""
        buckets: dict[tuple[str, str, str], ParsedSalesRow] = {}
        order: List[tuple[str, str, str]] = []
        for row in rows:
            customer = (row.customer_name or "").strip()
            product = (row.product or "").strip()
            period = (row.period or reporting_month or "").strip()
            if not customer or not product or not period:
                continue
            source_month = (getattr(row, "source_month", None) or "").strip()
            key = (
                customer.casefold(),
                product.casefold(),
                period.casefold(),
                (getattr(row, "location", "") or "").casefold(),
                source_month.casefold(),
            )
            qty = row.quantity if isinstance(row.quantity, Decimal) else Decimal(str(row.quantity))
            if key in buckets:
                existing = buckets[key]
                existing.quantity = Decimal(str(existing.quantity)) + qty
                existing.quantity_display = format_quantity(existing.quantity)
                existing.row_hash = build_sales_row_hash(
                    company,
                    existing.customer_name,
                    "",
                    existing.product,
                    existing.quantity,
                    period,
                    existing.source_month or "",
                )
            else:
                row.distributor = company
                row.company = company
                row.period = period
                row.segment = row.segment or ""
                row.location = getattr(row, "location", "") or ""
                row.quantity = qty
                row.quantity_display = format_quantity(qty)
                row.row_hash = build_sales_row_hash(
                    company, customer, "", product, qty, period, source_month
                )
                buckets[key] = row
                order.append(key)
        return [buckets[k] for k in order]

    def _retire_matching_file_reports(
        self,
        *,
        distributor_id: int,
        reporting_month: str,
        distributor_name: str,
        actor: str,
        file_name: str,
        company: Optional[str] = None,
    ) -> List[int]:
        """
        Soft-delete prior reports for the same company + quarter + Excel file.

        Different product files from the same distributor (9 files / quarter)
        must coexist — only replace when the same workbook is re-imported.
        """
        month = normalize_reporting_month(reporting_month)
        company_key = (company or "").strip() or distributor_name
        target_key = self._normalize_report_file_key(file_name)
        if not target_key:
            return []

        candidates = self.reports.list_active_for_company(company_key)
        if not candidates:
            candidates = self.reports.list_active_for_distributor(distributor_id)

        retired_ids: List[int] = []
        for existing in candidates:
            existing_month = normalize_reporting_month(existing.reporting_month)
            if existing_month.casefold() != month.casefold():
                continue
            existing_key = self._normalize_report_file_key(existing.file_name or existing.name)
            if existing_key != target_key:
                continue
            self._retire_active_report(
                existing,
                actor=actor,
                distributor_name=company_key,
                reporting_month=month,
                reason="Same-file Report Replacement",
            )
            retired_ids.append(existing.id)
        if retired_ids:
            logger.info(
                "Same-file replacement | company={} | month={} | file={} | retired={}",
                company_key,
                month,
                target_key,
                retired_ids,
            )
        return retired_ids

    def _retire_matching_active_reports(
        self,
        *,
        distributor_id: int,
        reporting_month: str,
        distributor_name: str,
        actor: str,
        company: Optional[str] = None,
    ) -> List[int]:
        """
        Soft-delete EVERY active report for this Distributor Company + Reporting Month.

        Scans all distributor rows that share the same company (handles legacy
        duplicate representative-based master rows). Quarters are retired when
        a Month YYYY report arrives.
        """
        import re

        month = normalize_reporting_month(reporting_month)
        retired_ids: List[int] = []
        is_month_yyyy = bool(re.match(r"^[A-Za-z]+ \d{4}$", month))
        company_key = (company or "").strip() or distributor_name

        candidates = self.reports.list_active_for_company(company_key)
        if not candidates:
            # Fallback: same distributor_id only
            candidates = self.reports.list_active_for_distributor(distributor_id)

        for existing in candidates:
            existing_month = normalize_reporting_month(existing.reporting_month)
            same_key = existing_month.casefold() == month.casefold()
            legacy_quarter = bool(
                is_month_yyyy and re.match(r"^Q[1-4]\b", existing_month or "", re.I)
            )
            if not same_key and not legacy_quarter:
                continue
            reason = (
                "Report Replacement"
                if same_key
                else "Legacy Quarter Retired (Reporting Quarter workflow)"
            )
            logger.info(
                "Report Replacement match | company={} | distributor_id={} | "
                "reporting_month={} | retiring_report_id={} | existing_month={!r} | reason={}",
                company_key,
                existing.distributor_id,
                month,
                existing.id,
                existing.reporting_month,
                reason,
            )
            self._retire_active_report(
                existing,
                actor=actor,
                distributor_name=company_key,
                reporting_month=month,
                reason=reason,
            )
            retired_ids.append(existing.id)
        if retired_ids:
            logger.info(
                "Report Replacement complete | company={} | reporting_month={} | retired_ids={}",
                company_key,
                month,
                retired_ids,
            )
        else:
            logger.info(
                "Report Replacement | no prior active report | company={} | reporting_month={}",
                company_key,
                month,
            )
        return retired_ids

    def ingest_excel(
        self,
        file_path: Path,
        *,
        source: ReportSource = ReportSource.UPLOAD,
        report_name: Optional[str] = None,
        email_message_id: Optional[int] = None,
        uploaded_by: Optional[int] = None,
        actor: str = "system",
        mark_duplicate_as_error: bool = True,
        reporting_quarter: Optional[str] = None,
        distributor_company: Optional[str] = None,
        distributor_id: Optional[int] = None,
    ) -> Tuple[Report, int, bool, int]:
        """
        Parse ERP Excel and insert sales records with business-aware replacement.

        Business identity: Distributor + Reporting Period (one active report).
        Distributor/quarter come from email/UI — not from the workbook.
        content_hash: exact file duplicate detection only.

        Returns ``(report, records_inserted, was_file_duplicate, quality_score)``.
        """
        content_hash = sha256_file(str(file_path))
        existing_file = self.reports.get_by_content_hash(content_hash)
        if existing_file:
            logger.warning(
                "Exact file duplicate | hash={} | existing_id={}",
                content_hash,
                existing_file.id,
            )
            if mark_duplicate_as_error:
                raise ConflictError(
                    "Duplicate report: this Excel file has already been processed",
                    details={
                        "existing_report_id": existing_file.id,
                        "content_hash": content_hash,
                        "duplicate_type": "file",
                    },
                )
            prior_score = existing_file.confidence_score or 0
            if not prior_score:
                cats = existing_file.categories or {}
                extraction = cats.get("extraction") if isinstance(cats, dict) else None
                if isinstance(extraction, dict) and extraction.get("quality_score") is not None:
                    prior_score = int(extraction["quality_score"])
            return existing_file, 0, True, prior_score

        # If distributor or quarter not explicitly provided, try extracting from Excel header cells (A1:B8)
        if not (distributor_company or distributor_id or email_message_id) or not reporting_quarter:
            try:
                from openpyxl import load_workbook
                wb_meta = load_workbook(file_path, read_only=True, data_only=True)
                ws_meta = wb_meta.active
                if ws_meta:
                    for r in range(1, 10):
                        lbl = str(ws_meta.cell(r, 1).value or "").strip().lower()
                        val = str(ws_meta.cell(r, 2).value or "").strip()
                        if val:
                            if not (distributor_company or distributor_id or email_message_id) and (
                                "company" in lbl or "distributor" in lbl or "person" in lbl
                            ):
                                distributor_company = distributor_company or val
                            if not reporting_quarter and (
                                "reporting" in lbl or "quarter" in lbl or "month" in lbl
                            ):
                                reporting_quarter = reporting_quarter or val
                wb_meta.close()
            except Exception:
                pass

        parse_result = self.parser.parse_workbook(
            file_path,
            reporting_quarter=reporting_quarter,
            distributor_label=(distributor_company or ""),
        )
        parsed_rows = parse_result.parsed_rows
        quality_score = parse_result.quality_score

        company, representative, reporting_month, primary_distributor_id, distributor_ids = (
            self._resolve_business_identity(
                parsed_rows,
                parse_result,
                reporting_quarter=reporting_quarter,
                distributor_company=distributor_company,
                distributor_id=distributor_id,
                email_message_id=email_message_id,
            )
        )

        logger.info(
            "Business identity resolved | company={} | representative={} | reporting_month={} | "
            "expected={} | imported={} | quality={}",
            company,
            representative,
            reporting_month,
            parse_result.expected_rows,
            parse_result.imported_rows,
            quality_score,
        )
        if parse_result.expected_rows != parse_result.imported_rows:
            logger.warning(
                "Expected vs Imported mismatch | expected={} | imported={}",
                parse_result.expected_rows,
                parse_result.imported_rows,
            )

        # Serialize concurrent replace for the same Company + Reporting Month.
        acquire_report_replace_lock(
            self.db,
            primary_distributor_id,
            reporting_month,
            company=company,
        )

        previous_ids = self._retire_matching_active_reports(
            distributor_id=primary_distributor_id,
            reporting_month=reporting_month,
            distributor_name=company,
            actor=actor,
            company=company,
        )
        previous_report_id: Optional[int] = previous_ids[0] if previous_ids else None
        if previous_ids:
            logger.info(
                "Report replacement | company={} | reporting_month={} | retired_ids={}",
                company,
                reporting_month,
                previous_ids,
            )

        name = report_name or file_path.name
        sender_meta = {
            "sender_name": None,
            "sender_email": None,
            "email_received_at": None,
            "graph_message_id": None,
            "internet_message_id": None,
            "mailbox": None,
        }
        if email_message_id:
            email_msg = self.emails.get_by_id(email_message_id)
            if email_msg:
                sender_meta = {
                    "sender_name": email_msg.sender_name,
                    "sender_email": email_msg.sender_email,
                    "email_received_at": email_msg.received_at,
                    "graph_message_id": email_msg.graph_message_id,
                    "internet_message_id": email_msg.internet_message_id,
                    "mailbox": email_msg.mailbox,
                }

        report = Report(
            name=name,
            description=f"Sales report ingested from {source.value}",
            report_type="Sales Report",
            status=ReportStatus.PROCESSING.value,
            source=source.value,
            reporting_month=reporting_month,
            report_date=utc_now(),
            file_name=file_path.name,
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            content_hash=content_hash,
            confidence_score=quality_score,
            categories={
                "products": sorted({r.product for r in parsed_rows}),
                "applications": [],
                "extraction": {
                    "parser": "erp",
                    "sheet_name": parse_result.sheet_name,
                    "sheet_score": parse_result.sheet_score,
                    "header_row": parse_result.header_row,
                    "mapping": parse_result.mapping,
                    "template_detected": False,
                    "sales_table_detected": parse_result.sales_table_detected,
                    "template_name": "erp",
                    "mapping_strategy": parse_result.mapping_strategy,
                    "expected_rows": parse_result.expected_rows,
                    "imported_rows": parse_result.imported_rows,
                    "incomplete_rows": parse_result.incomplete_rows,
                    "quality_score": quality_score,
                    "confidence_breakdown": parse_result.confidence_breakdown,
                    "distributor_details": {
                        "company": company,
                        "representative": representative,
                        "source": "sender_or_selection",
                    },
                    "replaced_report_id": previous_report_id,
                    "validation_summary": build_validation_summary(
                        expected_rows=parse_result.expected_rows,
                        imported_rows=parse_result.imported_rows,
                        incomplete_rows=parse_result.incomplete_rows,
                        row_errors=parse_result.row_errors or [],
                        confidence_score=quality_score,
                    ),
                },
            },
            distributor_id=primary_distributor_id,
            email_message_id=email_message_id,
            uploaded_by=uploaded_by,
            **sender_meta,
        )
        report = self.reports.create(report)

        try:
            entities = SalesRecordMapper.to_orm_many(
                parsed_rows,
                report_id=report.id,
                distributor_id_by_name=distributor_ids,
            )
            inserted = self.sales.bulk_insert(entities)
            if inserted <= 0:
                self.reports.soft_delete(report)
                raise ValidationAppError(
                    "No sales records inserted — refusing to keep an empty report",
                    details={"report_id": report.id},
                )
            # Phase-2: learn distributor → customer mappings from imported rows
            try:
                from app.services.distributor_service import DistributorService

                customer_names = [
                    (row.customer_name or "").strip()
                    for row in parsed_rows
                    if (row.customer_name or "").strip()
                ]
                logger.info(
                    "Learning customer mapping | distributor={} | customers={} | quarter={}",
                    primary_distributor_id,
                    customer_names,
                    reporting_month,
                )
                learned = DistributorService(self.db).learn_customers_from_import(
                    distributor_id=primary_distributor_id,
                    customer_names=customer_names,
                    source_report_id=report.id,
                    reporting_quarter=reporting_month,
                    actor=actor,
                )
                logger.info(
                    "Customer mapping learned | distributor_id={} | newly_learned={}",
                    primary_distributor_id,
                    learned,
                )
            except Exception:  # noqa: BLE001 — never fail ingest on mapping learn
                logger.exception(
                    "Customer mapping learn failed | report_id={} | distributor_id={}",
                    report.id,
                    primary_distributor_id,
                )

            self.reports.update(
                report,
                {
                    "status": ReportStatus.PROCESSED.value,
                    "record_count": inserted,
                    "confidence_score": quality_score,
                    "error_message": None,
                },
            )
            if previous_report_id:
                self.audit.log(
                    AuditTrailCreate(
                        user_name=actor,
                        action=AuditAction.REPLACED,
                        details=(
                            f"Report Replacement complete | previous_report_id={previous_report_id} | "
                            f"new_report_id={report.id} | company={company} | representative={representative} | "
                            f"reporting_month={reporting_month} | sender={report.sender_email} | "
                            f"records={inserted} | confidence={quality_score}"
                        ),
                        report_name=report.name,
                        entity_type="report",
                        entity_id=str(report.id),
                    )
                )
            else:
                self.audit.log(
                    AuditTrailCreate(
                        user_name=actor,
                        action=AuditAction.PROCESSED,
                        details=(
                            f"Processed sales report with {inserted} records "
                            f"(expected={parse_result.expected_rows}, quality={quality_score})"
                        ),
                        report_name=report.name,
                        entity_type="report",
                        entity_id=str(report.id),
                    )
                )
            logger.info(
                "Rows Inserted | report_id={} | count={} | quality_score={} | replaced={}",
                report.id,
                inserted,
                quality_score,
                previous_report_id,
            )
            return report, inserted, False, quality_score
        except ValidationAppError:
            raise
        except Exception as exc:
            self.sales.soft_delete_for_report(report.id)
            self.reports.update(
                report,
                {
                    "status": ReportStatus.FAILED.value,
                    "error_message": str(exc),
                },
            )
            self.reports.soft_delete(report)
            logger.exception("Failed to ingest report | path={}", file_path)
            raise ExcelProcessingError(f"Failed to insert sales records: {exc}") from exc

    async def upload_and_ingest(
        self,
        upload: UploadFile,
        *,
        actor: str = "system",
        uploaded_by: Optional[int] = None,
        reporting_quarter: Optional[str] = None,
        distributor_company: Optional[str] = None,
        distributor_id: Optional[int] = None,
    ) -> Tuple[Report, int, bool, int]:
        """Save an uploaded Excel and ingest it via the ERP parser."""
        path = await save_upload_file(upload, get_upload_subdir("reports"))
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.UPLOADED,
                details=f"Uploaded sales Excel {upload.filename}",
                report_name=upload.filename,
                entity_type="report",
            )
        )
        return self.ingest_excel(
            path,
            source=ReportSource.UPLOAD,
            report_name=upload.filename,
            uploaded_by=uploaded_by,
            actor=actor,
            reporting_quarter=reporting_quarter,
            distributor_company=distributor_company,
            distributor_id=distributor_id,
        )

    def _append_approved_rows(
        self,
        report: Report,
        parsed_rows: List[ParsedSalesRow],
        *,
        distributor_id: int,
        company: str,
        reporting_month: str,
        actor: str,
        quality_score: int,
    ) -> Tuple[Report, int, bool, int]:
        """Add new business rows onto the active quarter report. Do not replace it."""
        entities = SalesRecordMapper.to_orm_many(
            parsed_rows,
            report_id=report.id,
            distributor_id_by_name={company: distributor_id},
        )
        if not entities:
            raise ValidationAppError(DUPLICATE_SUBMISSION_MESSAGE)
        inserted = self.sales.bulk_insert(entities)
        try:
            from app.services.distributor_service import DistributorService

            DistributorService(self.db).learn_customers_from_import(
                distributor_id=distributor_id,
                customer_names=[r.customer_name for r in parsed_rows],
                source_report_id=report.id,
                reporting_quarter=reporting_month,
                actor=actor,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Customer mapping learn failed during quarter append")
        self.reports.update(
            report,
            {
                "status": ReportStatus.PROCESSED.value,
                "record_count": int(report.record_count or 0) + inserted,
                "confidence_score": quality_score,
                "error_message": None,
            },
        )
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.PROCESSED,
                details=(
                    f"ERP quarter append | report_id={report.id} | "
                    f"distributor_id={distributor_id} | period={reporting_month} | "
                    f"rows_added={inserted}"
                ),
                entity_type="report",
                entity_id=str(report.id),
            )
        )
        return report, inserted, False, quality_score

    def persist_approved_rows(
        self,
        file_path: Path,
        parsed_rows: List[ParsedSalesRow],
        *,
        quality_score: int,
        source: ReportSource = ReportSource.OUTLOOK,
        report_name: Optional[str] = None,
        email_message_id: Optional[int] = None,
        actor: str = "system",
        reporting_quarter: str,
        distributor_id: int,
        mark_duplicate_as_error: bool = False,
        confidence_breakdown: Optional[dict] = None,
        workbook_meta: Optional[dict] = None,
    ) -> Tuple[Report, int, bool, int]:
        """
        Persist already-approved ERP rows (preview → approve flow).

        Uses file content_hash for exact-file dedupe. Does not re-parse Excel.
        """
        if not parsed_rows:
            raise ValidationAppError("No sales records to import")

        content_hash = sha256_file(str(file_path))
        # One workbook can feed multiple FY quarters — scope file dedupe per quarter.
        quarter_scoped_hash = sha256_bytes(f"{content_hash}|{reporting_quarter.strip()}".encode("utf-8"))
        existing_file = self.reports.get_by_content_hash(quarter_scoped_hash)
        if existing_file:
            raise ValidationAppError(DUPLICATE_SUBMISSION_MESSAGE)

        dist = self.distributors.get_or_raise(distributor_id)
        company = (dist.company or dist.name or "").strip()
        representative = (dist.contact_person or dist.name or company).strip()
        reporting_month = normalize_reporting_month(reporting_quarter)
        if not reporting_month:
            raise ValidationAppError("reporting_quarter is required (e.g. FY 2025-26 • Q3)")

        parsed_rows = self._aggregate_parsed_rows(
            list(parsed_rows),
            company=company,
            reporting_month=reporting_month,
        )
        if not parsed_rows:
            raise ValidationAppError("No sales records to import after aggregation")

        acquire_report_replace_lock(
            self.db, distributor_id, reporting_month, company=company
        )
        existing_report = self.reports.get_active_by_business_key(
            distributor_id, reporting_month
        )
        if existing_report is not None:
            return self._append_approved_rows(
                existing_report,
                parsed_rows,
                distributor_id=distributor_id,
                company=company,
                reporting_month=reporting_month,
                actor=actor,
                quality_score=quality_score,
            )
        previous_report_id = None

        sender_meta = {
            "sender_name": None,
            "sender_email": None,
            "email_received_at": None,
            "graph_message_id": None,
            "internet_message_id": None,
            "mailbox": None,
        }
        if email_message_id:
            email_msg = self.emails.get_by_id(email_message_id)
            if email_msg:
                sender_meta = {
                    "sender_name": email_msg.sender_name,
                    "sender_email": email_msg.sender_email,
                    "email_received_at": email_msg.received_at,
                    "graph_message_id": email_msg.graph_message_id,
                    "internet_message_id": email_msg.internet_message_id,
                    "mailbox": email_msg.mailbox,
                }

        meta = workbook_meta or {}
        report = Report(
            name=report_name or file_path.name,
            description=f"ERP sales report approved from {source.value}",
            report_type="Sales Report",
            status=ReportStatus.PROCESSING.value,
            source=source.value,
            reporting_month=reporting_month,
            report_date=utc_now(),
            file_name=file_path.name,
            file_path=str(file_path),
            file_size=file_path.stat().st_size if file_path.exists() else 0,
            content_hash=quarter_scoped_hash,
            confidence_score=quality_score,
            categories={
                "products": sorted({r.product for r in parsed_rows}),
                "applications": [],
                "extraction": {
                    "parser": "erp",
                    "approved_import": True,
                    "sheet_name": meta.get("sheet_name"),
                    "expected_rows": len(parsed_rows),
                    "imported_rows": len(parsed_rows),
                    "incomplete_rows": 0,
                    "quality_score": quality_score,
                    "confidence_breakdown": confidence_breakdown or {},
                    "replaced_report_id": previous_report_id,
                    "validation_summary": build_validation_summary(
                        expected_rows=len(parsed_rows),
                        imported_rows=len(parsed_rows),
                        incomplete_rows=0,
                        row_errors=[],
                        confidence_score=quality_score,
                    ),
                },
            },
            distributor_id=distributor_id,
            email_message_id=email_message_id,
            **sender_meta,
        )
        report = self.reports.create(report)
        report_id = report.id
        try:
            entities = SalesRecordMapper.to_orm_many(
                parsed_rows,
                report_id=report.id,
                distributor_id_by_name={company: distributor_id},
            )
            inserted = self.sales.bulk_insert(entities)
            if inserted <= 0:
                self.reports.soft_delete(report)
                raise ValidationAppError("No sales records inserted")
            try:
                from app.services.distributor_service import DistributorService

                DistributorService(self.db).learn_customers_from_import(
                    distributor_id=distributor_id,
                    customer_names=[r.customer_name for r in parsed_rows],
                    source_report_id=report.id,
                    reporting_quarter=reporting_month,
                    actor=actor,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Customer mapping learn failed during approved import")

            self.reports.update(
                report,
                {
                    "status": ReportStatus.PROCESSED.value,
                    "record_count": inserted,
                    "confidence_score": quality_score,
                    "error_message": None,
                },
            )
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.PROCESSED,
                    details=(
                        f"ERP approved import | report_id={report.id} | "
                        f"company={company} | quarter={reporting_month} | records={inserted}"
                    ),
                    report_name=report.name,
                    entity_type="report",
                    entity_id=str(report.id),
                )
            )
            return report, inserted, False, quality_score
        except Exception:
            # Do not soft_delete here: IntegrityError leaves the Session unusable.
            # get_db() rolls back the whole request (including this report create).
            logger.exception(
                "Approved import failed | report_id={} | company={} | quarter={}",
                report_id,
                company,
                reporting_month,
            )
            raise

    def to_frontend_reports(self, reports: List[Report]) -> List[FrontendReport]:
        """Map reports to frontend ExistingReports shape."""
        result: List[FrontendReport] = []
        for report in reports:
            categories = report.categories or {}
            extraction = categories.get("extraction") if isinstance(categories, dict) else None
            validation = None
            incomplete = None
            imported = None
            expected = None
            validation_message = None
            if isinstance(extraction, dict):
                validation = extraction.get("validation_summary")
                incomplete = extraction.get("incomplete_rows")
                imported = extraction.get("imported_rows")
                expected = extraction.get("expected_rows")
                if isinstance(validation, dict):
                    # Keep confidence on summary for older reports that lack it
                    if validation.get("confidence_score") is None and report.confidence_score is not None:
                        validation = {**validation, "confidence_score": report.confidence_score}
                    from app.utils.validation_summary import validation_user_message

                    validation_message = validation_user_message(validation)
            result.append(
                FrontendReport(
                    id=str(report.id),
                    name=report.name,
                    date=format_report_date(report.report_date or report.created_at),
                    type=report.report_type,
                    description=report.description or "",
                    categories=ReportCategories(
                        products=list(categories.get("products") or []),
                        applications=list(categories.get("applications") or []),
                    ),
                    confidenceScore=report.confidence_score,
                    expectedRows=expected,
                    importedRows=imported,
                    incompleteRows=incomplete,
                    validationSummary=validation if isinstance(validation, dict) else None,
                    validationMessage=validation_message,
                )
            )
        return result

    def filter_categories(self) -> dict:
        """Return product/application filter options for reports UI."""
        products = self.sales.distinct_products()
        from sqlalchemy import distinct, select

        from app.models.report import Report
        from app.models.sales_record import SalesRecord

        segments = list(
            self.db.scalars(
                select(distinct(SalesRecord.segment))
                .select_from(SalesRecord)
                .join(Report, Report.id == SalesRecord.report_id)
                .where(
                    SalesRecord.is_deleted.is_(False),
                    Report.is_deleted.is_(False),
                    SalesRecord.segment.is_not(None),
                    SalesRecord.segment != "",
                )
                .order_by(SalesRecord.segment.asc())
            ).all()
        )
        return {
            "products": products
            or [
                "NBR",
                "NBR - PVC Polyblend",
                "HSR",
                "PNBR",
                "SB Latex",
                "Pure Acrylic Latex",
                "XSB Latex",
                "Styrene Acrylic Latex",
                "Vinyl Pyridine Latex",
                "XNB Latex",
                "NBR Latex",
            ],
            "applications": segments
            or [
                "Paper and Paperboard",
                "Carpet",
                "Construction and waterproofing",
                "Textiles",
                "Tyre cord",
                "Gloves",
                "Specialty",
            ],
        }

    def suggested_questions(self) -> List[str]:
        """Suggested chat questions for reports UI."""
        return [
            "What are the key trends in this report?",
            "Which market performed best?",
            "Summarize the insights",
        ]

    def consolidated_records(
        self,
        *,
        skip: int = 0,
        limit: int = 5000,
        period: Optional[str] = None,
        product: Optional[str] = None,
    ) -> List[FrontendSalesRecord]:
        """Return flat frontend sales rows (legacy helper; prefers report groups API)."""
        from app.services.consolidated_data_service import ConsolidatedDataService

        page = ConsolidatedDataService(self.db).list_records(
            skip=skip,
            limit=limit,
            period=period,
            product=product,
        )
        flat: List[FrontendSalesRecord] = []
        for group in page.data:
            for line in group.sales:
                flat.append(
                    FrontendSalesRecord(
                        id=line.id,
                        reportId=group.reportId,
                        srNo=line.srNo,
                        distributor=group.distributor,
                        company=group.company,
                        customerName=line.customerName,
                        segment=line.segment,
                        product=line.product,
                        quantity=line.quantity,
                        reportingMonth=group.reportingMonth,
                        period=group.reportingMonth,
                        importedAt=group.importedAt,
                        senderName=group.senderName,
                        senderEmail=group.senderEmail,
                        emailReceivedAt=group.emailReceivedAt,
                        mailbox=group.mailbox,
                        confidenceScore=group.confidenceScore,
                    )
                )
        return flat
