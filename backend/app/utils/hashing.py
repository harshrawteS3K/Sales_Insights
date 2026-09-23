"""Hashing and content fingerprint helpers."""

import hashlib
from decimal import Decimal
from typing import Any


def sha256_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest for raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    """Return SHA-256 hex digest for a file on disk."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(*parts: Any) -> str:
    """Return SHA-256 hex digest for concatenated normalized parts."""
    payload = "|".join("" if part is None else str(part).strip().lower() for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_sales_row_hash(
    distributor: str,
    customer_name: str,
    segment: str,
    product: str,
    quantity: Decimal | float | str,
    period: str,
    source_month: str = "",
) -> str:
    """Build a stable hash for duplicate sales-row detection."""
    return sha256_text(
        distributor, customer_name, segment, product, quantity, period, source_month
    )
