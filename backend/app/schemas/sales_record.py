"""Sales record and consolidated-data schemas (report-centric)."""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import TimestampSchema


class SalesRecordBase(BaseModel):
    """Shared sales record fields (transactional only)."""

    sr_no: Optional[int] = None
    customer_name: str
    segment: str
    location: str = ""
    product: str
    quantity: Decimal
    quantity_display: Optional[str] = None
    period: Optional[str] = None  # denormalized reporting quarter / month
    unit: str = "MT"


class SalesRecordCreate(SalesRecordBase):
    """Create sales record payload."""

    report_id: int
    distributor_id: Optional[int] = None
    row_hash: str


class SalesRecordResponse(SalesRecordBase, TimestampSchema):
    """Sales record API response."""

    id: int
    report_id: int
    distributor_id: Optional[int] = None
    row_hash: str
    is_deleted: bool = False


class SalesLineItem(BaseModel):
    """Transactional sales row inside a report group (no repeated report metadata)."""

    id: int
    srNo: int
    customerName: str
    segment: str
    location: str = ""
    product: str
    quantity: str


class ReportSalesGroup(BaseModel):
    """One report with its sales rows — report metadata shown once."""

    reportId: int
    distributor: str
    company: Optional[str] = None
    distributorId: Optional[int] = None
    location: Optional[str] = None
    # DB column remains reporting_month; API exposes reporting_quarter as primary.
    reportingQuarter: Optional[str] = None
    reportingMonth: Optional[str] = None  # backward-compat alias of reportingQuarter
    senderName: Optional[str] = None
    senderEmail: Optional[str] = None
    emailReceivedAt: Optional[str] = None
    mailbox: Optional[str] = None
    importedAt: Optional[str] = None
    confidenceScore: Optional[int] = None
    status: Optional[str] = None
    recordCount: int = 0
    expectedRows: Optional[int] = None
    importedRows: Optional[int] = None
    incompleteRows: Optional[int] = None
    validationSummary: Optional[dict] = None
    validationMessage: Optional[str] = None
    sales: List[SalesLineItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_reporting_quarter(self) -> "ReportSalesGroup":
        value = (self.reportingQuarter or self.reportingMonth or "").strip() or None
        self.reportingQuarter = value
        self.reportingMonth = value
        return self


# Backward-compatible flat shape (still used by some clients / exports)
class FrontendSalesRecord(BaseModel):
    """Flat sales row (legacy). Prefer ReportSalesGroup for UI."""

    id: int
    reportId: int
    srNo: int
    distributor: str
    company: Optional[str] = None
    customerName: str
    segment: str
    location: str = ""
    product: str
    quantity: str
    reportingQuarter: Optional[str] = None
    reportingMonth: Optional[str] = None  # backward-compat
    period: Optional[str] = None
    importedAt: Optional[str] = None
    senderName: Optional[str] = None
    senderEmail: Optional[str] = None
    emailReceivedAt: Optional[str] = None
    mailbox: Optional[str] = None
    graphMessageId: Optional[str] = None
    internetMessageId: Optional[str] = None
    confidenceScore: Optional[int] = None

    @model_validator(mode="after")
    def _sync_reporting_quarter(self) -> "FrontendSalesRecord":
        value = (self.reportingQuarter or self.reportingMonth or self.period or "").strip() or None
        self.reportingQuarter = value
        self.reportingMonth = value
        self.period = value
        return self


class ConsolidatedFilterOptions(BaseModel):
    """Dynamic filter dropdown values (all from SELECT DISTINCT)."""

    distributors: List[str] = Field(default_factory=list)
    customers: List[str] = Field(default_factory=list)
    segments: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    products: List[str] = Field(default_factory=list)
    companies: List[str] = Field(default_factory=list)
    reportingQuarters: List[str] = Field(default_factory=list)
    reportingMonths: List[str] = Field(default_factory=list)  # alias of reportingQuarters
    periods: List[str] = Field(default_factory=list)  # alias
    quarters: List[str] = Field(default_factory=list)
    quantityUnit: str = "MT"

    @model_validator(mode="after")
    def _sync_quarters(self) -> "ConsolidatedFilterOptions":
        values = self.reportingQuarters or self.reportingMonths or self.periods or []
        self.reportingQuarters = list(values)
        self.reportingMonths = list(values)
        self.periods = list(values)
        if not self.quarters:
            self.quarters = list(values)
        return self


class QuarterlySummaryRow(BaseModel):
    """One Distributor Company in a quarterly business summary."""

    company: str
    quarter: str
    totalQuantity: float
    totalQuantityDisplay: str
    unit: str = "MT"
    productsSold: int = 0
    customerCount: int = 0
    reportsIncluded: int = 0
    monthsSubmitted: List[str] = Field(default_factory=list)
    monthsExpected: List[str] = Field(default_factory=list)
    isPartial: bool = False


class QuarterlyPeriodInfo(BaseModel):
    """Resolved period metadata."""

    label: str
    kind: str
    year: Optional[int] = None
    months: List[str] = Field(default_factory=list)


class QuarterlySummaryResponse(BaseModel):
    """GET /consolidated-data/quarterly/summary."""

    success: bool = True
    period: QuarterlyPeriodInfo
    unit: str = "MT"
    totalCompanies: int = 0
    grandTotalQuantity: float = 0
    data: List[QuarterlySummaryRow] = Field(default_factory=list)


class QuarterlyProductRow(BaseModel):
    """Legacy product line (kept for older clients). Prefer QuarterlyDetailRow."""

    product: str
    quantity: float
    quantityDisplay: str
    unit: str = "MT"
    contributionPct: float = 0
    customerCount: int = 0


class QuarterlyDetailRow(BaseModel):
    """Customer × Segment × Product line in a virtual quarterly report."""

    srNo: int
    customer: str
    segment: str
    product: str
    quantity: float
    quantityDisplay: str
    unit: str = "MT"
    contributionPct: float = 0


class QuarterlyReportResponse(BaseModel):
    """GET /consolidated-data/quarterly/report — virtual report (not persisted)."""

    success: bool = True
    period: QuarterlyPeriodInfo
    company: str
    unit: str = "MT"
    totalQuantity: float = 0
    totalQuantityDisplay: str = "0"
    productsSold: int = 0
    customerCount: int = 0
    reportsIncluded: int = 0
    monthsSubmitted: List[str] = Field(default_factory=list)
    monthsExpected: List[str] = Field(default_factory=list)
    isPartial: bool = False
    items: List[QuarterlyDetailRow] = Field(default_factory=list)
    totalRecords: int = 0
    totalPages: int = 0
    currentPage: int = 1
    pageSize: int = 10
    # Deprecated: empty for new clients; use ``items``
    products: List[QuarterlyProductRow] = Field(default_factory=list)


class PeriodSummaryItem(BaseModel):
    """Accurate period rollup across the full filtered set (not just one page)."""

    label: str
    distributorCount: int = 0
    reportCount: int = 0
    totalQuantity: float = 0


class ConsolidatedRecordsPage(BaseModel):
    """Paginated consolidated sales — report-grouped."""

    success: bool = True
    data: List[ReportSalesGroup]
    total: int  # total matching sales rows
    totalReports: int = 0
    skip: int = 0
    limit: int = 50
    pageBy: str = "rows"  # rows | reports
    periodSummaries: List[PeriodSummaryItem] = Field(default_factory=list)


class DeleteReportRequest(BaseModel):
    """Delete all sales rows for a distributor + reporting quarter."""

    distributor: str = Field(..., min_length=1)
    reportingQuarter: Optional[str] = None
    reportingMonth: Optional[str] = None  # backward-compat alias of reportingQuarter
    period: Optional[str] = None  # legacy alias

    def resolved_month(self) -> str:
        return (self.reportingQuarter or self.reportingMonth or self.period or "").strip()

    @model_validator(mode="after")
    def _sync_reporting_quarter(self) -> "DeleteReportRequest":
        value = (self.reportingQuarter or self.reportingMonth or self.period or "").strip() or None
        self.reportingQuarter = value
        self.reportingMonth = value
        self.period = value
        return self


class DeleteReportPreview(BaseModel):
    """Preview of rows that would be deleted for a report unit."""

    distributor: str
    reportingQuarter: Optional[str] = None
    reportingMonth: Optional[str] = None
    period: Optional[str] = None  # legacy alias
    rowCount: int

    @model_validator(mode="after")
    def _sync_reporting_quarter(self) -> "DeleteReportPreview":
        value = (self.reportingQuarter or self.reportingMonth or self.period or "").strip() or None
        self.reportingQuarter = value
        self.reportingMonth = value
        self.period = value
        return self


class DeleteResult(BaseModel):
    """Result of a delete operation."""

    success: bool = True
    message: str
    deletedCount: int = 0


class SalesRecordListResponse(BaseModel):
    """List of sales records."""

    success: bool = True
    data: List[SalesRecordResponse]
    total: int


class ParsedSalesRow(BaseModel):
    """Normalized row produced by Excel parser."""

    sr_no: Optional[int] = None
    distributor: str
    customer_name: str
    segment: str
    location: str = ""
    product: str
    quantity: Decimal
    quantity_display: str
    period: Optional[str] = None  # denormalized reporting quarter
    unit: str = "MT"
    company: Optional[str] = None
    row_hash: str = ""
    errors: List[str] = Field(default_factory=list)
