"""Application enumerations."""

from enum import Enum


class UserRole(str, Enum):
    """RBAC roles supported by the application."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


class OutlookSyncPermission(str, Enum):
    """Persona permission for Outlook mailbox synchronization."""

    NONE = "none"
    OWN = "own"
    ALL = "all"


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
    """Audit trail action types (enterprise business events)."""

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
    LOGOUT = "Logout"
    FAILED = "Failed"
    EXPORTED = "Exported"
    GENERATED = "Generated"
    SEARCHED = "Searched"
    FILTERED = "Filtered"
    OPENED = "Opened"
    EXTRACTED = "Extract Emails"
    WARNING = "Warning"
    AUTOMATED_OUTLOOK_SYNC = "Automated Outlook Sync"
    MANUAL_OUTLOOK_SYNC = "Manual Outlook Sync"


class AuditModule(str, Enum):
    """Application modules for audit classification."""

    EMAILS = "Emails"
    CONSOLIDATED = "Consolidated Data"
    VISUALIZATION = "Visualization"
    MASTER_DATA = "Master Data"
    SETTINGS = "Settings"
    AUTHENTICATION = "Authentication"
    DASHBOARD = "Dashboard"
    USER_MANAGEMENT = "User Management"
    SYSTEM = "System"


class AuditStatus(str, Enum):
    """Outcome badge for an audit event."""

    SUCCESS = "Success"
    WARNING = "Warning"
    FAILED = "Failed"
    INFO = "Info"


class EmailProcessStatus(str, Enum):
    """Processing status for Outlook emails."""

    UNREAD = "unread"
    DOWNLOADED = "downloaded"
    PARSED = "parsed"
    INSERTED = "inserted"
    MARKED_READ = "marked_read"
    FAILED = "failed"
    SKIPPED = "skipped"
    INVALID_SUBJECT = "invalid_subject"


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
