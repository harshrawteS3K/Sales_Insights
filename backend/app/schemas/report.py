"""Report schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.enums import ReportSource, ReportStatus
from app.schemas.common import TimestampSchema


class ReportCategories(BaseModel):
    """Frontend-aligned report categories."""

    products: List[str] = Field(default_factory=list)
    applications: List[str] = Field(default_factory=list)


class ReportBase(BaseModel):
    """Shared report fields."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    report_type: str = "Sales Report"
    reporting_month: Optional[str] = None
    categories: Optional[ReportCategories] = None


class ReportCreate(ReportBase):
    """Manual report create payload."""

    distributor_id: Optional[int] = None
    source: ReportSource = ReportSource.MANUAL
    status: ReportStatus = ReportStatus.PENDING


class ReportUpdate(BaseModel):
    """Report update payload."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    report_type: Optional[str] = None
    reporting_month: Optional[str] = None
    status: Optional[ReportStatus] = None
    categories: Optional[ReportCategories] = None
    distributor_id: Optional[int] = None


class ReportResponse(TimestampSchema):
    """Report API response (backend shape)."""

    id: int
    public_id: str
    name: str
    description: Optional[str] = None
    report_type: str = "Sales Report"
    reporting_month: Optional[str] = None
    categories: Optional[Any] = None
    status: str
    source: str
    report_date: Optional[datetime] = None
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    content_hash: Optional[str] = None
    record_count: int = 0
    confidence_score: Optional[int] = None
    error_message: Optional[str] = None
    distributor_id: Optional[int] = None
    email_message_id: Optional[int] = None
    uploaded_by: Optional[int] = None
    is_deleted: bool = False


class FrontendReport(BaseModel):
    """Frontend ExistingReports shape: GET /api/reports."""

    id: str
    name: str
    date: str
    type: str
    description: str
    categories: ReportCategories


class ReportFilterCategories(BaseModel):
    """GET /api/reports/filter-categories."""

    products: List[str]
    applications: List[str]


class ReportListResponse(BaseModel):
    """List of reports."""

    success: bool = True
    data: List[ReportResponse]
    total: int


class ReportUploadResponse(BaseModel):
    """Response after uploading and parsing a sales Excel."""

    success: bool = True
    message: str
    report: ReportResponse
    records_inserted: int
    duplicates_skipped: bool = False
