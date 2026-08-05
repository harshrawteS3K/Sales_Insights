"""Dashboard and visualization schemas (frontend-aligned)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KpiItem(BaseModel):
    """Frontend KPI card item."""

    label: str
    value: str


class ProductQty(BaseModel):
    """Product quantity aggregation."""

    product: str
    qty: float


class DistributorTotal(BaseModel):
    """Distributor totals aggregation."""

    name: str
    qty: float
    customers: int
    products: int
    avgOrder: float


class DashboardSummary(BaseModel):
    """High-level dashboard summary."""

    total_distributors: int
    total_reports: int
    total_sales_records: int
    total_quantity: float
    total_emails_processed: int
    pending_reports: int
    failed_reports: int
    last_sync_at: Optional[str] = None
    kpis: List[KpiItem] = Field(default_factory=list)


class FilterOptions(BaseModel):
    """Filter option maps for visualizations."""

    product: Optional[List[str]] = None
    distributor: Optional[List[str]] = None
    period: List[str] = Field(default_factory=list)


class MasterDataUploadResponse(BaseModel):
    """Master data upload / replace result."""

    success: bool = True
    status: str = "success"
    message: str
    records_imported: int = 0
    duplicates_ignored: int = 0
    processing_time_ms: float = 0
    # Backward-compatible aliases
    records_upserted: int = 0
    records_skipped: int = 0
    errors: List[str] = Field(default_factory=list)
    # Customer Master replace accounting (explicit; never silent)
    excel_rows: int = 0
    blank_customer_name: int = 0
    duplicate_names: int = 0
    validation_errors: int = 0


class TemplateGenerateResponse(BaseModel):
    """Distributor template generation result."""

    success: bool = True
    status: str = "ready"
    message: str
    template_version: str
    file_name: str
    customers_count: int = 0
    products_count: int = 0
    generated_at: str


class CustomerMasterResponse(BaseModel):
    """Customer master row."""

    model_config = {"from_attributes": True}

    id: int
    customer_name: str
    customer_code: Optional[str] = None
    segment: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    is_active: bool = True


class ProductMasterResponse(BaseModel):
    """Product master row."""

    model_config = {"from_attributes": True}

    id: int
    industry_type: str
    product_code: str
    product_name: Optional[str] = None
    segment: Optional[str] = None
    description: Optional[str] = None
    unit: str = "KG"
    is_active: bool = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    app: str
    version: str
    environment: str
    database: str
    timestamp: str


class HealthProbeResponse(BaseModel):
    """Liveness / readiness probe response."""

    success: bool = True
    status: str
    database: Optional[str] = None


class CustomerMasterListResponse(BaseModel):
    """Paginated-style customer master list (backend contract)."""

    success: bool = True
    data: List[CustomerMasterResponse]
    total: int


class ProductMasterListResponse(BaseModel):
    """Paginated-style product master list (backend contract)."""

    success: bool = True
    data: List[ProductMasterResponse]
    total: int
