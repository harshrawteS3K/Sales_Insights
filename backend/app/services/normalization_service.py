"""Read-only access to product alias mappings (Super Admin)."""

from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.distributor import Distributor
from app.models.product_alias_mapping import ProductAliasMapping
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.normalization import ProductMappingRow


def _distributor_label():
    return func.coalesce(
        func.nullif(func.trim(Distributor.company), ""),
        Distributor.name,
    )


class NormalizationService:
    """Lists mappings. Does not read or write ``sales_records``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_product_mappings(
        self,
        *,
        distributor: Optional[str] = None,
        original_product: Optional[str] = None,
        normalized_product: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse[ProductMappingRow]:
        label = _distributor_label()
        query = (
            select(
                ProductAliasMapping.id,
                ProductAliasMapping.distributor_id,
                label.label("distributor_name"),
                ProductAliasMapping.original_product_name,
                ProductAliasMapping.normalized_product_name,
            )
            .select_from(ProductAliasMapping)
            .outerjoin(Distributor, Distributor.id == ProductAliasMapping.distributor_id)
            .where(ProductAliasMapping.is_active.is_(True))
        )
        dist = (distributor or "").strip()
        if dist:
            # Global mappings (no distributor) apply to every distributor.
            pattern = f"%{dist.lower()}%"
            query = query.where(
                or_(
                    ProductAliasMapping.distributor_id.is_(None),
                    func.lower(func.coalesce(Distributor.company, "")).like(pattern),
                    func.lower(func.coalesce(Distributor.name, "")).like(pattern),
                )
            )
        original = (original_product or "").strip()
        if original:
            query = query.where(
                func.lower(ProductAliasMapping.original_product_name).like(f"%{original.lower()}%")
            )
        normalized = (normalized_product or "").strip()
        if normalized:
            query = query.where(
                func.lower(ProductAliasMapping.normalized_product_name).like(
                    f"%{normalized.lower()}%"
                )
            )

        total = int(
            self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = self.db.execute(
            query.order_by(ProductAliasMapping.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return PaginatedResponse[ProductMappingRow](
            data=[
                ProductMappingRow(
                    id=row.id,
                    distributor_id=row.distributor_id,
                    distributor_name=row.distributor_name,
                    original_product_name=row.original_product_name,
                    normalized_product_name=row.normalized_product_name,
                )
                for row in rows
            ],
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=math.ceil(total / page_size) if total else 0,
            ),
        )
