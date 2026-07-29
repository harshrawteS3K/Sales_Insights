"""Shared application constants."""

from pathlib import Path

from app.core.config import BASE_DIR

API_TITLE = "APCOTEX Sales Insights API"
API_DESCRIPTION = (
    "Enterprise Sales Insights platform for Apcotex Industries. "
    "Provides Outlook email ingestion, Excel sales report processing, "
    "distributor analytics, master data management, and audit logging."
)
API_VERSION = "1.0.0"
OPENAPI_TAGS = [
    {"name": "Health", "description": "Service health and readiness probes"},
    {"name": "Users", "description": "User management and RBAC roles"},
    {"name": "Reports", "description": "Sales and market research reports"},
    {"name": "Distributors", "description": "Distributor master and details"},
    {"name": "Dashboard", "description": "Dashboard KPIs and analytics aggregates"},
    {"name": "Outlook Sync", "description": "Microsoft Graph mailbox synchronization"},
    {"name": "Master Data", "description": "Customer/product master uploads and templates"},
    {"name": "Audit Logs", "description": "System audit trail"},
    {"name": "Emails", "description": "Extracted distributor email metadata"},
    {"name": "Consolidated Data", "description": "Consolidated sales records"},
    {"name": "Visualizations", "description": "Chart-ready aggregation endpoints"},
]

EXCEL_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
}

ALLOWED_EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}

# Chart palette aligned with frontend PRODUCT_COLORS (theme.ts)
PRODUCT_MIX_COLORS = [
    "#1F5FA8",
    "#1FB7B5",
    "#7C3AED",
    "#059669",
    "#D97706",
    "#D93A2F",
    "#0891B2",
    "#9333EA",
    "#16A34A",
    "#DC2626",
    "#0D9488",
]
PRODUCT_MIX_OTHERS_COLOR = "#D1D5DB"

SALES_REPORT_REQUIRED_COLUMNS = [
    "distributor",
    "customer_name",
    "segment",
    "product",
    "quantity",
]

# Sales-table columns required when Distributor Name lives in the header block
SALES_REPORT_TABLE_REQUIRED_COLUMNS = [
    "customer_name",
    "segment",
    "product",
    "quantity",
]

# Unified fallback vocabulary (also includes official APCOTEX display forms).
# Used ONLY when the workbook is not an exact official-template match.
SALES_REPORT_COLUMN_ALIASES = {
    "distributor": [
        "distributor",
        "distributor name",
        "name of distributor",
        "distributor_name",
        "sales person",
        "salesperson",
    ],
    "sr_no": [
        "sr no",
        "sr. no",
        "sr. no.",
        "sr_no",
        "s no",
        "serial no",
        "serial number",
        "sno",
        "#",
    ],
    "customer_name": [
        "name of customer",
        "customer name",
        "customer_name",
        "customer-name",
        "customer",
        "customername",
        "buyer",
        "buyer name",
        "name of the customer",
    ],
    "segment": [
        "segment",
        "application",
        "category",
        "industry",
    ],
    "product": [
        "product",
        "product name",
        "product_name",
        "grade",
        "sku",
    ],
    "opening_stock": [
        "opening stock",
        "opening_stock",
        "opening-stock",
        "open stock",
        "openingstock",
        "op stock",
        "op. stock",
        "opening qty",
        "opening quantity",
    ],
    "closing_stock": [
        "closing stock",
        "closing_stock",
        "closing-stock",
        "close stock",
        "closingstock",
        "cl stock",
        "cl. stock",
        "closing qty",
        "closing quantity",
    ],
    "quantity": [
        "quantity",
        "qty",
        "qty kg",
        "qty (kg)",
        "quantity kg",
        "quantity (kg)",
        "volume",
        "qty_kg",
    ],
    # Legacy per-row period (final template uses Reporting Month in header only)
    "period": [
        "period",
        "reporting period",
        "quarter",
        "month",
        "fy period",
    ],
}

# Phase 2: only CUSTOMER NAME is mandatory
CUSTOMER_MASTER_REQUIRED_COLUMNS = [
    "customer_name",
]

# Phase 2: Industry Type Description + Product Code
PRODUCT_MASTER_REQUIRED_COLUMNS = [
    "industry_type",
    "product_code",
]

DEFAULT_SEGMENTS = [
    "Carpet",
    "Paper and Paperboard",
    "Construction and waterproofing",
    "Textiles",
    "Tyre cord",
    "Gloves",
    "Specialty",
]

DISTRIBUTOR_TEMPLATE_SHEET = "Sales Report"
DISTRIBUTOR_TEMPLATE_FILENAME = "distributor_sales_template.xlsx"

UPLOAD_MASTER_DIR = Path(BASE_DIR) / "uploads" / "master"
UPLOAD_REPORTS_DIR = Path(BASE_DIR) / "uploads" / "reports"
UPLOAD_ATTACHMENTS_DIR = Path(BASE_DIR) / "uploads" / "attachments"
DOWNLOADS_DIR = Path(BASE_DIR) / "downloads"
TEMPLATES_DIR = Path(BASE_DIR) / "templates"

MAX_UPLOAD_SIZE_MB = 25
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

GRAPH_EXCEL_CONTENT_TYPES = EXCEL_MIME_TYPES
