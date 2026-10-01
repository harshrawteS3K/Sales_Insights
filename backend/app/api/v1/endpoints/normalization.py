"""Product normalization endpoints (Super Admin only)."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.rbac import RequireSuperAdmin
from app.schemas.common import PaginatedResponse
from app.schemas.normalization import ProductMappingRow
from app.services.normalization_service import NormalizationService

router = APIRouter(prefix="/normalization", tags=["Normalization"])


def get_normalization_service(db: Annotated[Session, Depends(get_db)]) -> NormalizationService:
    return NormalizationService(db)


@router.get(
    "/product-mappings",
    response_model=PaginatedResponse[ProductMappingRow],
    summary="Distributor product → normalized product mappings (Super Admin)",
)
def list_product_mappings(
    _: RequireSuperAdmin,
    service: Annotated[NormalizationService, Depends(get_normalization_service)],
    distributor: Optional[str] = Query(None),
    original_product: Optional[str] = Query(None),
    normalized_product: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> PaginatedResponse[ProductMappingRow]:
    return service.list_product_mappings(
        distributor=distributor,
        original_product=original_product,
        normalized_product=normalized_product,
        page=page,
        page_size=page_size,
    )
