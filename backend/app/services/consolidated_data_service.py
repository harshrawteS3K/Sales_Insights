"""Consolidated Sales Data management service (report-centric)."""

from collections import OrderedDict
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.enums import AuditAction
from app.exceptions import NotFoundError, ValidationAppError
from app.repositories.report_repository import ReportRepository
from app.repositories.sales_record_repository import SalesRecordRepository
from app.schemas.audit import AuditTrailCreate
from app.schemas.sales_record import (
    ConsolidatedFilterOptions,
    ConsolidatedRecordsPage,
    DeleteReportPreview,
    DeleteResult,
    PeriodSummaryItem,
    ReportSalesGroup,
    SalesLineItem,
)
from app.services.audit_service import AuditService
from app.utils.datetime_utils import format_frontend_datetime
from app.utils.quantity import format_quantity

logger = get_logger(__name__)


class ConsolidatedDataService:
    """Enterprise sales data management: list, filter, delete, audit."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sales = SalesRecordRepository(db)
        self.reports = ReportRepository(db)
        self.audit = AuditService(db)

    def filter_options(self) -> ConsolidatedFilterOptions:
        """Load all filter dropdown values via SELECT DISTINCT (no hardcoding)."""
        from app.services.business_aggregation_service import BusinessAggregationService
        from app.services.business_aggregation_service import QUANTITY_UNIT

        months = self.sales.distinct_column_values("period")
        companies = self.sales.distinct_distributors_with_sales()
        quarters = BusinessAggregationService(self.db).available_quarters()
        return ConsolidatedFilterOptions(
            # Primary reporting entity = Distributor Company
            distributors=companies,
            customers=self.sales.distinct_column_values("customer"),
            segments=self.sales.distinct_column_values("segment"),
            products=self.sales.distinct_column_values("product"),
            companies=companies,
            reportingQuarters=months,
            reportingMonths=months,
            periods=months,
            quarters=quarters or months,
            quantityUnit=QUANTITY_UNIT,
        )

    def list_records(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
        distributor: Optional[str] = None,
        customer: Optional[str] = None,
        segment: Optional[str] = None,
        product: Optional[str] = None,
        company: Optional[str] = None,
        period: Optional[str] = None,
        reporting_month: Optional[str] = None,
        quarter: Optional[str] = None,
        quantity_min: Optional[float] = None,
        quantity_max: Optional[float] = None,
        imported_from: Optional[date] = None,
        imported_to: Optional[date] = None,
        sort_by: str = "id",
        sort_dir: str = "asc",
        actor: Optional[str] = None,
        audit_search: bool = False,
        page_by: str = "reports",
    ) -> ConsolidatedRecordsPage:
        """
        Server-side filtered sales, returned as report groups.

        ``page_by=reports`` (default for UI): paginate complete distributor reports
        so quarter headers are not built from a mid-report sales-row slice.

        ``page_by=rows``: legacy sales-row pagination.

        ``periodSummaries`` always reflects the full filtered set (accurate counts).
        """
        month = (reporting_month or period or None)
        filter_kwargs = dict(
            search=search,
            distributor=distributor,
            customer=customer,
            segment=segment,
            product=product,
            company=company,
            period=month,
            quarter=quarter,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            imported_from=imported_from,
            imported_to=imported_to,
        )
        total = self.sales.count_filtered(**filter_kwargs)
        total_reports = self.sales.count_matching_reports(**filter_kwargs)
        summaries_raw = self.sales.period_summaries(**filter_kwargs)
        period_summaries = [PeriodSummaryItem(**row) for row in summaries_raw]

        mode = (page_by or "reports").strip().lower()
        if mode not in {"reports", "rows"}:
            mode = "reports"

        if mode == "reports":
            report_ids = self.sales.list_matching_report_ids(
                skip=skip,
                limit=limit,
                **filter_kwargs,
            )
            records = self.sales.list_for_report_ids(
                report_ids,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
            groups = self._group_by_report(records, base_idx=0)
            # Keep report order from pagination query
            order = {rid: i for i, rid in enumerate(report_ids)}
            groups.sort(key=lambda g: order.get(g.reportId, 10**9))
        else:
            records = self.sales.list_with_distributor(
                skip=skip,
                limit=limit,
                sort_by=sort_by,
                sort_dir=sort_dir,
                **filter_kwargs,
            )
            groups = self._group_by_report(records, base_idx=skip)

        if actor and audit_search and (
            search or distributor or customer or segment or product or company or month or quarter
        ):
            parts = []
            if search:
                parts.append(f"search={search!r}")
            for label, val in [
                ("distributor", distributor),
                ("customer", customer),
                ("segment", segment),
                ("product", product),
                ("company", company),
                ("reporting_month", month),
                ("quarter", quarter),
            ]:
                if val:
                    parts.append(f"{label}={val}")
            self.audit.log(
                AuditTrailCreate(
                    user_name=actor,
                    action=AuditAction.VIEWED,
                    details=f"Filtered consolidated sales data ({', '.join(parts)}; {total} matches)",
                    entity_type="consolidated_data",
                )
            )

        return ConsolidatedRecordsPage(
            data=groups,
            total=total,
            totalReports=total_reports,
            skip=skip,
            limit=limit,
            pageBy=mode,
            periodSummaries=period_summaries,
        )

    def delete_record(self, record_id: int, *, actor: str) -> DeleteResult:
        """Soft-delete a single sales record."""
        record = self.sales.get_or_raise(record_id)
        distributor_name = record.distributor.name if record.distributor else ""
        customer = record.customer_name
        month = record.period
        report_id = record.report_id

        self.sales.soft_delete(record)

        if report_id and self.sales.count_active_for_report(report_id) == 0:
            report = self.reports.get_by_id(report_id)
            if report and not report.is_deleted:
                self.reports.soft_delete(report)

        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DELETED,
                details=(
                    f"Deleted sales record id={record_id} | customer={customer} | "
                    f"distributor={distributor_name} | reporting_quarter={month}"
                ),
                report_name=None,
                entity_type="sales_record",
                entity_id=str(record_id),
            )
        )
        return DeleteResult(message="Sales record deleted", deletedCount=1)

    def preview_delete_report(self, distributor: str, reporting_month: str) -> DeleteReportPreview:
        """Return how many rows would be deleted for distributor + reporting quarter."""
        if not distributor.strip() or not reporting_month.strip():
            raise ValidationAppError("Distributor and Reporting Quarter are required")
        count = self.sales.count_by_distributor_period(distributor, reporting_month)
        return DeleteReportPreview(
            distributor=distributor,
            reportingQuarter=reporting_month,
            reportingMonth=reporting_month,
            period=reporting_month,
            rowCount=count,
        )

    def delete_report(self, distributor: str, reporting_month: str, *, actor: str) -> DeleteResult:
        """Soft-delete the active business report for Distributor + Reporting Quarter."""
        if not distributor.strip() or not reporting_month.strip():
            raise ValidationAppError("Distributor and Reporting Quarter are required")

        count = self.sales.count_by_distributor_period(distributor, reporting_month)
        if count == 0:
            raise NotFoundError(
                f"No sales records found for distributor={distributor!r} "
                f"reporting_quarter={reporting_month!r}"
            )

        deleted, report_ids = self.sales.soft_delete_by_distributor_period(
            distributor, reporting_month
        )

        for report_id in report_ids:
            report = self.reports.get_by_id(report_id)
            if report and not report.is_deleted:
                self.sales.soft_delete_for_report(report_id)
                self.reports.soft_delete(report)

        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DELETED,
                details=(
                    f"Deleted imported report | distributor={distributor} | "
                    f"reporting_quarter={reporting_month} | rows_deleted={deleted} | "
                    f"reports_soft_deleted={report_ids}"
                ),
                report_name=f"{distributor} / {reporting_month}",
                entity_type="sales_report",
                entity_id=f"{distributor}|{reporting_month}",
            )
        )
        return DeleteResult(
            message=(
                f"Deleted {deleted} sales records for {distributor} / {reporting_month}"
            ),
            deletedCount=deleted,
        )

    def log_export(self, *, actor: str, total: int, filters_summary: str = "") -> None:
        """Audit export of filtered consolidated data."""
        self.audit.log(
            AuditTrailCreate(
                user_name=actor,
                action=AuditAction.DOWNLOADED,
                details=f"Exported Quarterly Report ({total} rows){filters_summary}",
                entity_type="consolidated_data",
            )
        )

    def _group_by_report(self, records, *, base_idx: int) -> List[ReportSalesGroup]:
        """Collapse flat sales rows into report groups (metadata once)."""
        groups: "OrderedDict[int, ReportSalesGroup]" = OrderedDict()
        for i, record in enumerate(records):
            report = getattr(record, "report", None)
            dist = record.distributor
            report_id = record.report_id
            if report_id not in groups:
                if report is not None and getattr(report, "is_deleted", False):
                    # Defense: never surface archived reports even if orphan sales leaked
                    continue
                reporting_month = None
                if report and getattr(report, "reporting_month", None):
                    reporting_month = report.reporting_month
                elif record.period:
                    reporting_month = record.period
                imported = None
                if report and getattr(report, "created_at", None):
                    imported = format_frontend_datetime(report.created_at)
                elif getattr(record, "created_at", None):
                    imported = format_frontend_datetime(record.created_at)
                email_received = None
                if report and getattr(report, "email_received_at", None):
                    email_received = format_frontend_datetime(report.email_received_at)
                extraction = {}
                validation_summary = None
                validation_message = None
                expected_rows = None
                imported_rows = None
                incomplete_rows = None
                if report and isinstance(getattr(report, "categories", None), dict):
                    extraction = (report.categories or {}).get("extraction") or {}
                    if isinstance(extraction, dict):
                        validation_summary = extraction.get("validation_summary")
                        expected_rows = extraction.get("expected_rows")
                        imported_rows = extraction.get("imported_rows")
                        incomplete_rows = extraction.get("incomplete_rows")
                        if isinstance(validation_summary, dict):
                            conf = getattr(report, "confidence_score", None)
                            if validation_summary.get("confidence_score") is None and conf is not None:
                                validation_summary = {
                                    **validation_summary,
                                    "confidence_score": conf,
                                }
                        from app.utils.validation_summary import validation_user_message

                        validation_message = validation_user_message(
                            validation_summary if isinstance(validation_summary, dict) else None
                        )
                groups[report_id] = ReportSalesGroup(
                    reportId=report_id,
                    distributor=dist.name if dist else "",
                    company=(dist.company if dist else None) or None,
                    distributorId=dist.id if dist else (getattr(report, "distributor_id", None) if report else None),
                    reportingQuarter=reporting_month,
                    reportingMonth=reporting_month,
                    senderName=getattr(report, "sender_name", None) if report else None,
                    senderEmail=getattr(report, "sender_email", None) if report else None,
                    emailReceivedAt=email_received,
                    mailbox=getattr(report, "mailbox", None) if report else None,
                    importedAt=imported,
                    confidenceScore=getattr(report, "confidence_score", None) if report else None,
                    status=getattr(report, "status", None) if report else None,
                    recordCount=0,
                    expectedRows=expected_rows,
                    importedRows=imported_rows,
                    incompleteRows=incomplete_rows,
                    validationSummary=validation_summary if isinstance(validation_summary, dict) else None,
                    validationMessage=validation_message,
                    sales=[],
                )
            line = SalesLineItem(
                id=record.id,
                srNo=record.sr_no or (base_idx + i + 1),
                customerName=record.customer_name,
                segment=record.segment,
                product=record.product,
                quantity=record.quantity_display or format_quantity(record.quantity),
            )
            groups[report_id].sales.append(line)
            groups[report_id].recordCount = len(groups[report_id].sales)
        return list(groups.values())
