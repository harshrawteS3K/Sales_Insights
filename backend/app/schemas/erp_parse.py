"""ERP Excel parse + approve-import schemas."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ERPMappingItem(BaseModel):
    """One header mapping result."""

    field: Optional[str] = None
    original: Optional[str] = None
    mapped: str
    confidence: float = 0
    method: str = "none"
    column: Optional[int] = None
    column_index: Optional[int] = None


class ERPConfidenceBlock(BaseModel):
    """Accuracy summary for preview UI (legacy name: confidence)."""

    overall: float
    accuracy: Optional[float] = None
    customer: float = 0
    product: float = 0
    quantity: float = 0
    band: str = "red"
    breakdown: Dict[str, Any] = Field(default_factory=dict)


class ERPPreviewRow(BaseModel):
    """Normalized preview row (period set for monthly→quarterly expansion)."""

    customer_name: str
    product: str
    sales_quantity: float
    period: Optional[str] = None
    reporting_quarter: Optional[str] = None


class ERPDistributorOption(BaseModel):
    id: int
    company: str
    name: Optional[str] = None
    email: Optional[str] = None
    match: Optional[str] = None


class ERPAvailableColumn(BaseModel):
    index: int
    header: str
    column: int


class ERPParsePreviewResponse(BaseModel):
    """Preview response (no import)."""

    sheet_name: str
    sheet_score: float = 0
    header_row: int = 0
    confidence: ERPConfidenceBlock
    accuracy: Optional[float] = None
    mapping: List[ERPMappingItem] = Field(default_factory=list)
    column_positions: Dict[str, Optional[int]] = Field(default_factory=dict)
    rows: List[ERPPreviewRow] = Field(default_factory=list)
    row_count: int = 0
    candidate_sheets: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    workbook_name: Optional[str] = None
    email_id: Optional[int] = None
    subject: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    distributor_matches: List[ERPDistributorOption] = Field(default_factory=list)
    all_distributors: List[ERPDistributorOption] = Field(default_factory=list)
    distributor_id: Optional[int] = None
    distributor_unknown: bool = False
    import_allowed: bool = False
    available_columns: List[ERPAvailableColumn] = Field(default_factory=list)
    monthly_pivot: bool = False
    fiscal_year_start: Optional[int] = None
    mapping_source: Optional[str] = Field(
        default="python",
        description="python | llm | manual — which engine produced column mapping",
    )
    attachment_count: int = 1
    attachment_names: List[str] = Field(default_factory=list)
    attachments_capped: bool = False
    detected_quarter: Optional[str] = None
    quarter_confidence: Optional[float] = None
    subject_valid: bool = True
    parsed_distributor: Optional[str] = None
    parsed_location: Optional[str] = None
    parsed_segment: Optional[str] = None


class ERPEmailPreviewRequest(BaseModel):
    """Optional remapping when previewing an email attachment."""

    mapping: Optional[Union[List[ERPMappingItem], Dict[str, Any]]] = None
    fiscal_year_start: Optional[int] = Field(default=None, ge=1990, le=2100)


class ERPImportRequest(BaseModel):
    """Approve import after AI preview."""

    email_id: int
    distributor_id: Optional[int] = None
    reporting_quarter: Optional[str] = Field(default=None, min_length=3, max_length=50)
    fiscal_year_start: Optional[int] = Field(default=None, ge=1990, le=2100)
    mapping: Optional[Union[List[ERPMappingItem], Dict[str, Any]]] = None
    rows: Optional[List[ERPPreviewRow]] = None


class ERPImportResponse(BaseModel):
    report_id: int
    records_inserted: int
    duplicate: bool = False
    quality_score: int = 0
    distributor_id: int
    reporting_quarter: str
    workbook_name: Optional[str] = None
    workbooks_imported: List[str] = Field(default_factory=list)
    workbook_skips: List[Dict[str, Any]] = Field(default_factory=list)
    reports_created: int = 1
    quarters_imported: List[str] = Field(default_factory=list)