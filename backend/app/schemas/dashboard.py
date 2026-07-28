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
    """Master data upload result."""

    success: bool = True
    message: str
    records_upserted: int
    records_skipped: int = 0
    errors: List[str] = Field(default_factory=list)


class CustomerMasterResponse(BaseModel):
    """Customer master row."""

    model_config = {"from_attributes": True}

    id: int
    customer_code: str
    customer_name: str
    segment: str
    region: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    is_active: bool = True


class ProductMasterResponse(BaseModel):
    """Product master row."""

    model_config = {"from_attributes": True}

    id: int
    product_code: str
    product_name: str
    segment: str
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
