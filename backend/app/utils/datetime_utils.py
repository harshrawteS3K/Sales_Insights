"""Datetime formatting helpers."""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def format_frontend_datetime(value: datetime) -> str:
    """Format datetime as ``26 Jun 2026, 09:14`` for emails UI."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime("%d %b %Y, %H:%M")


def format_audit_timestamp(value: datetime) -> str:
    """Format datetime as ``2026-05-02 14:30:00`` for audit UI."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_report_date(value: Optional[datetime]) -> str:
    """Format report date as ``YYYY-MM-DD``."""
    if value is None:
        return utc_now().strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d")
