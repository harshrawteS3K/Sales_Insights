"""PostgreSQL advisory locks for serializing replace operations."""

import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.utils.distributor_name import normalize_company_name, normalize_distributor_name
from app.utils.reporting_month import normalize_reporting_month

logger = get_logger(__name__)

# Stable 64-bit keys (namespace for APCOTEX master replace)
CUSTOMER_MASTER_REPLACE_LOCK = 8_742_100_001
PRODUCT_MASTER_REPLACE_LOCK = 8_742_100_002


def acquire_xact_lock(db: Session, lock_key: int, *, label: str = "resource") -> None:
    """
    Acquire a transaction-scoped advisory lock.

    Blocks until the lock is free. Released automatically on COMMIT or ROLLBACK.
    Safe under concurrent admin uploads — no deadlock with a single lock key per resource.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    logger.debug("Acquired advisory xact lock | key={} | label={}", lock_key, label)


def report_replace_lock_key(distributor_id: int, reporting_month: str) -> int:
    """Legacy lock key by distributor_id (prefer company-based lock)."""
    month = normalize_reporting_month(reporting_month).casefold()
    payload = f"report-replace|{int(distributor_id)}|{month}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def report_replace_lock_key_company(company: str, reporting_month: str) -> int:
    """
    Derive advisory lock key for Distributor Company + Reporting Month.

    This is the correct business-identity lock — representatives do not affect it.
    """
    company_key = normalize_distributor_name(company) or normalize_company_name(company).casefold()
    month = normalize_reporting_month(reporting_month).casefold()
    payload = f"report-replace-company|{company_key}|{month}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def report_replace_lock_keys(distributor_id: int, reporting_month: str) -> tuple[int, int]:
    return report_replace_lock_key(distributor_id, reporting_month), 0


def acquire_report_replace_lock(
    db: Session,
    distributor_id: int,
    reporting_month: str,
    *,
    company: str | None = None,
) -> None:
    """
    Serialize report replacement for one Company + Reporting Month identity.

    When ``company`` is provided, locks on company (preferred). Otherwise falls
    back to distributor_id for legacy callers.
    """
    if company and normalize_company_name(company):
        key = report_replace_lock_key_company(company, reporting_month)
        label_company = normalize_company_name(company)
    else:
        key = report_replace_lock_key(distributor_id, reporting_month)
        label_company = f"distributor_id={distributor_id}"
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    logger.info(
        "Acquired report replace lock | company={} | reporting_month={} | key={}",
        label_company,
        normalize_reporting_month(reporting_month),
        key,
    )
