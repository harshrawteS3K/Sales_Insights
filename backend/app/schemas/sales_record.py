"""Sales record and consolidated-data schemas (report-centric)."""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import TimestampSchema


class SalesRecordBase(BaseModel):
    """Shared sales record fields (transactional only)."""

    sr_no: Optional[int] = None
    customer_name: str
    segment: str
    product: str
    opening_stock: Optional[Decimal] = None
    closing_stock: Optional[Decimal] = None
    quantity: Decimal
    quantity_display: Optional[str] = None
    period: Optional[str] = None  # legacy denormalized reporting month
    unit: str = "KG"


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
    product: str
    quantity: str
    openingStock: Optional[str] = None
    closingStock: Optional[str] = None


class ReportSalesGroup(BaseModel):
    """One report with its sales rows — report metadata shown once."""

    reportId: int
    distributor: str
    company: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    reportingMonth: Optional[str] = None
    senderName: Optional[str] = None
    senderEmail: Optional[str] = None
    emailReceivedAt: Optional[str] = None
    mailbox: Optional[str] = None
    importedAt: Optional[str] = None
    confidenceScore: Optional[int] = None
    status: Optional[str] = None
    recordCount: int = 0
    sales: List[SalesLineItem] = Field(default_factory=list)


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
    product: str
    openingStock: Optional[str] = None
    closingStock: Optional[str] = None
    quantity: str
    reportingMonth: Optional[str] = None
    period: Optional[str] = None  # alias of reportingMonth for older clients
    importedAt: Optional[str] = None
    senderName: Optional[str] = None
    senderEmail: Optional[str] = None
    emailReceivedAt: Optional[str] = None
    mailbox: Optional[str] = None
    graphMessageId: Optional[str] = None
    internetMessageId: Optional[str] = None
    confidenceScore: Optional[int] = None


class ConsolidatedFilterOptions(BaseModel):
    """Dynamic filter dropdown values (all from SELECT DISTINCT)."""

    distributors: List[str] = Field(default_factory=list)
    customers: List[str] = Field(default_factory=list)
    segments: List[str] = Field(default_factory=list)
    products: List[str] = Field(default_factory=list)
    companies: List[str] = Field(default_factory=list)
    reportingMonths: List[str] = Field(default_factory=list)
    # Legacy aliases
    periods: List[str] = Field(default_factory=list)
    quarters: List[str] = Field(default_factory=list)


class ConsolidatedRecordsPage(BaseModel):
    """Paginated consolidated sales — report-grouped."""

    success: bool = True
    data: List[ReportSalesGroup]
    total: int  # total matching sales rows (for pagination of flat filter hits)
    totalReports: int = 0
    skip: int = 0
    limit: int = 50


class DeleteReportRequest(BaseModel):
    """Delete all sales rows for a distributor + reporting month."""

    distributor: str = Field(..., min_length=1)
    reportingMonth: Optional[str] = None
    period: Optional[str] = None  # legacy alias

    def resolved_month(self) -> str:
        return (self.reportingMonth or self.period or "").strip()


class DeleteReportPreview(BaseModel):
    """Preview of rows that would be deleted for a report unit."""

    distributor: str
    reportingMonth: str
    period: Optional[str] = None  # legacy alias
    rowCount: int


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
    product: str
    opening_stock: Optional[Decimal] = None
    closing_stock: Optional[Decimal] = None
    quantity: Decimal
    quantity_display: str
    period: Optional[str] = None  # denormalized reporting month
    unit: str = "KG"
    company: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    row_hash: str = ""
    errors: List[str] = Field(default_factory=list)
