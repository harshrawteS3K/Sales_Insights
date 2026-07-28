"""Distributor endpoints."""

from typing import Dict, Optional

from fastapi import APIRouter, Query, status

from app.dependencies.rbac import CurrentUser, RequireAdmin, RequireUser
from app.dependencies.services import DistributorServiceDep
from app.schemas.common import DataResponse, MessageResponse
from app.schemas.distributor import (
    DistributorCreate,
    DistributorInfo,
    DistributorListResponse,
    DistributorResponse,
    DistributorUpdate,
)

router = APIRouter(prefix="/distributors", tags=["Distributors"])


@router.get("", response_model=DistributorListResponse, summary="List distributors")
def list_distributors(
    service: DistributorServiceDep,
    _: RequireUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
) -> DistributorListResponse:
    """List distributors."""
    items = service.list_distributors(skip=skip, limit=limit, search=search)
    return DistributorListResponse(
        data=[DistributorResponse.model_validate(i) for i in items],
        total=service.count_distributors(search=search),
    )


@router.get(
    "/details-map",
    response_model=DataResponse[Dict[str, DistributorInfo]],
    summary="Distributor details map",
)
def distributor_details_map(
    service: DistributorServiceDep,
    _: RequireUser,
) -> DataResponse[Dict[str, DistributorInfo]]:
    """Frontend-aligned distributor detail map."""
    return DataResponse(data=service.details_map())


@router.get(
    "/{distributor_id}",
    response_model=DataResponse[DistributorResponse],
    summary="Get distributor",
)
def get_distributor(
    distributor_id: int,
    service: DistributorServiceDep,
    _: RequireUser,
) -> DataResponse[DistributorResponse]:
    """Get distributor by id."""
    item = service.get_distributor(distributor_id)
    return DataResponse(data=DistributorResponse.model_validate(item))


@router.post(
    "",
    response_model=DataResponse[DistributorResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create distributor",
)
def create_distributor(
    payload: DistributorCreate,
    service: DistributorServiceDep,
    current: RequireAdmin,
) -> DataResponse[DistributorResponse]:
    """Create distributor (Admin only)."""
    item = service.create_distributor(payload, actor=current.name)
    return DataResponse(data=DistributorResponse.model_validate(item), message="Distributor created")


@router.put(
    "/{distributor_id}",
    response_model=DataResponse[DistributorResponse],
    summary="Update distributor",
)
def update_distributor(
    distributor_id: int,
    payload: DistributorUpdate,
    service: DistributorServiceDep,
    current: RequireAdmin,
) -> DataResponse[DistributorResponse]:
    """Update distributor (Admin only)."""
    item = service.update_distributor(distributor_id, payload, actor=current.name)
    return DataResponse(data=DistributorResponse.model_validate(item), message="Distributor updated")


@router.delete("/{distributor_id}", response_model=MessageResponse, summary="Delete distributor")
def delete_distributor(
    distributor_id: int,
    service: DistributorServiceDep,
    current: RequireAdmin,
) -> MessageResponse:
    """Soft-delete distributor (Admin only)."""
    service.delete_distributor(distributor_id, actor=current.name)
    return MessageResponse(message=f"Distributor {distributor_id} deleted")
