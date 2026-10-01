"""Product normalization mapping schemas."""

from typing import Optional

from pydantic import BaseModel


class ProductMappingRow(BaseModel):
    """One distributor product name and the normalized name it maps to."""

    id: int
    distributor_id: Optional[int] = None
    distributor_name: Optional[str] = None
    original_product_name: str
    normalized_product_name: str
