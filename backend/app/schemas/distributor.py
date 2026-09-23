"""Distributor schemas."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import TimestampSchema


class DistributorBase(BaseModel):
    """Shared distributor fields."""

    name: str = Field(..., min_length=1, max_length=255)
    company: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(default=None, max_length=64)
    contact_person: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    email: Optional[EmailStr] = None
    cc_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    region: Optional[str] = Field(default=None, max_length=150)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=20)
    is_active: bool = True
    notes: Optional[str] = None


class DistributorCreate(DistributorBase):
    """Create distributor payload."""

    pass


class DistributorUpdate(BaseModel):
    """Update distributor payload."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    company: Optional[str] = Field(default=None, min_length=1, max_length=255)
    code: Optional[str] = Field(default=None, max_length=64)
    contact_person: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    email: Optional[EmailStr] = None
    cc_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    region: Optional[str] = Field(default=None, max_length=150)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class DistributorResponse(DistributorBase, TimestampSchema):
    """Distributor API response."""

    id: int
    is_deleted: bool = False
    customer_count: int = 0
    country: str = ""


class DistributorInfo(BaseModel):
    """Frontend-aligned distributor info shape (Consolidated Data details)."""

    name: str
    company: str
    address: str = ""
    phone: str = ""


class DistributorListResponse(BaseModel):
    """List of distributors."""

    success: bool = True
    data: List[DistributorResponse]
    total: int


class QuarterlyPackageRequest(BaseModel):
    """Create Outlook draft for one distributor + quarter."""

    reporting_quarter: str = Field(..., min_length=3, max_length=50)


class BulkEmailDraftRequest(BaseModel):
    """Create Outlook drafts for many distributors (one shared quarter)."""

    distributor_ids: List[int] = Field(..., min_length=1, max_length=100)
    reporting_quarter: str = Field(..., min_length=3, max_length=50)


class BulkEmailDraftItemResult(BaseModel):
    """Per-distributor outcome inside a bulk job."""

    distributor_id: int
    distributor_name: str
    success: bool
    reason: Optional[str] = None
    draft_id: Optional[str] = None
    attachment_name: Optional[str] = None
    recipient: Optional[str] = None


class BulkEmailDraftJobStartResponse(BaseModel):
    """Returned immediately when a bulk job is accepted."""

    job_id: str
    status: str
    total: int
    reporting_quarter: str


class BulkEmailDraftJobStatusResponse(BaseModel):
    """Polled progress / final result for a bulk draft job."""

    job_id: str
    status: str
    reporting_quarter: str
    total: int
    processed: int
    successful: int
    failed: int
    results: List[BulkEmailDraftItemResult] = Field(default_factory=list)
    error: Optional[str] = None


class EmailDraftResponse(BaseModel):
    """Result of creating a Microsoft Graph Outlook draft."""

    success: bool = True
    message: str
    mailbox: str
    distributor_id: int
    distributor_name: str
    reporting_quarter: str
    draft_id: str
    attachment_name: str
    recipient: str
    cc: Optional[str] = None


class TemplateGenerateRequest(BaseModel):
    """Master Data template generation options."""

    mode: str = Field(
        default="generic",
        description="generic | distributor",
    )
    distributor_id: Optional[int] = None
    reporting_quarter: Optional[str] = None
