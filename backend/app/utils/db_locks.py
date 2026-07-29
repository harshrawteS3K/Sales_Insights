"""PostgreSQL advisory locks for serializing replace operations."""

import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
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
    """
    Derive a stable signed 64-bit advisory lock key for Distributor + Reporting Month.

    Uses normalized month so concurrent uploads with equivalent month strings
    serialize on the same business identity.
    """
    month = normalize_reporting_month(reporting_month).casefold()
    payload = f"report-replace|{int(distributor_id)}|{month}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    # PostgreSQL pg_advisory_xact_lock(bigint) expects a signed 64-bit value.
    return int.from_bytes(digest, "big", signed=True)


# Back-compat alias used by tests / callers expecting a pair — returns (key, 0).
def report_replace_lock_keys(distributor_id: int, reporting_month: str) -> tuple[int, int]:
    return report_replace_lock_key(distributor_id, reporting_month), 0


def acquire_report_replace_lock(
    db: Session,
    distributor_id: int,
    reporting_month: str,
) -> None:
    """
    Serialize report replacement for one Distributor + Reporting Month identity.

    Uses ``pg_advisory_xact_lock(bigint)``. Distinct identities hash to different
    keys and do not block each other. Released on COMMIT/ROLLBACK.
    """
    key = report_replace_lock_key(distributor_id, reporting_month)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    logger.info(
        "Acquired report replace lock | distributor_id={} | reporting_month={} | key={}",
        distributor_id,
        normalize_reporting_month(reporting_month),
        key,
    )
