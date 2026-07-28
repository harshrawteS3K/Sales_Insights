"""Application enumerations."""

from enum import Enum


class UserRole(str, Enum):
    """RBAC roles supported by the application."""

    ADMIN = "admin"
    USER = "user"


class ReportStatus(str, Enum):
    """Lifecycle status of a distributor sales report."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class ReportSource(str, Enum):
    """Origin of a sales report."""

    OUTLOOK = "outlook"
    UPLOAD = "upload"
    MANUAL = "manual"


class AuditAction(str, Enum):
    """Audit trail action types (aligned with frontend)."""

    CREATED = "Created"
    UPDATED = "Updated"
    DELETED = "Deleted"
    VIEWED = "Viewed"
    SYNCED = "Synced"
    UPLOADED = "Uploaded"
    DOWNLOADED = "Downloaded"
    PROCESSED = "Processed"
    REPLACED = "Report Replacement"
    LOGIN = "Login"
    FAILED = "Failed"


class EmailProcessStatus(str, Enum):
    """Processing status for Outlook emails."""

    UNREAD = "unread"
    DOWNLOADED = "downloaded"
    PARSED = "parsed"
    INSERTED = "inserted"
    MARKED_READ = "marked_read"
    FAILED = "failed"
    SKIPPED = "skipped"


class MasterDataType(str, Enum):
    """Master data workbook types."""

    CUSTOMER = "customer"
    PRODUCT = "product"


class SegmentType(str, Enum):
    """Business segments used in sales reporting."""

    CARPET = "Carpet"
    PAPER = "Paper and Paperboard"
    CONSTRUCTION = "Construction and waterproofing"
    TEXTILES = "Textiles"
    TYRE_CORD = "Tyre cord"
    GLOVES = "Gloves"
    SPECIALTY = "Specialty"
    OTHER = "Other"


class SyncStatus(str, Enum):
    """Outlook sync job status."""

    STARTED = "started"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
