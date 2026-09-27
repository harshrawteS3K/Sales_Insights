"""Shared ERP ingest constants."""

from app.core.logging import get_logger
from app.erp_parser.header_mapper import normalize_header_text

logger = get_logger(__name__)

MAX_EXCEL_ATTACHMENTS_PER_EMAIL = 20
MIN_IMPORT_ACCURACY = 75.0
DUPLICATE_REVIEW_MESSAGE = (
    "Duplicate records detected for this Financial Year & Quarter. Review before proceeding."
)

_FIELD_ALIASES = {
    "customer": "customer",
    "customer name": "customer",
    "customer_name": "customer",
    "product": "product",
    "sales quantity": "quantity",
    "sales_quantity": "quantity",
    "quantity": "quantity",
    "ignored": "ignored",
    "ignore": "ignored",
}


def _normalize_mapped_field(value: str) -> str:
    key = normalize_header_text(value)
    return _FIELD_ALIASES.get(key, key)
