"""Distributor endpoints.

Template / Outlook draft package endpoints below are DEPRECATED for UI —
ERP email ingest (Preview → Approve Import) is the production path.
Endpoints remain mounted for API compatibility only.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query, status

from app.dependencies.rbac import RequireAdmin, RequireUser
from app.dependencies.services import DistributorServiceDep, MasterDataServiceDep
from app.exceptions import NotFoundError
from app.schemas.common import DataResponse, MessageResponse
from app.schemas.distributor import (
    BulkEmailDraftJobStartResponse,
    BulkEmailDraftJobStatusResponse,
    BulkEmailDraftRequest,
    DistributorCreate,
    DistributorInfo,
    DistributorListResponse,
    DistributorResponse,
    DistributorUpdate,
    EmailDraftResponse,
    QuarterlyPackageRequest,
)
from app.services import bulk_email_draft_service

router = APIRouter(prefix="/distributors", tags=["Distributors"])


def _to_response(service: DistributorServiceDep, item) -> DistributorResponse:
    data = DistributorResponse.model_validate(item)
    data.customer_count = service.customer_count(item.id)
    return data


@router.get("", response_model=DistributorListResponse, summary="List distributors")
def list_distributors(
    service: DistributorServiceDep,
    _: RequireUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    active_only: bool = Query(False),
) -> DistributorListResponse:
    """List distributors."""
    items = service.list_distributors(
        skip=skip, limit=limit, search=search, active_only=active_only
    )
    return DistributorListResponse(
        data=[_to_response(service, i) for i in items],
        total=service.count_distributors(search=search, active_only=active_only),
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


@router.post(
    "/backfill-customer-mappings",
    response_model=DataResponse[dict],
    summary="Backfill distributor customer mappings from ACTIVE sales",
)
def backfill_customer_mappings(
    service: DistributorServiceDep,
    current: RequireAdmin,
) -> DataResponse[dict]:
    """Rebuild mappings from existing ACTIVE reports/sales (idempotent)."""
    result = service.backfill_customer_mappings(actor=current.name)
    return DataResponse(
        data=result,
        message=(
            f"Backfill complete: {result.get('newly_learned', 0)} new mappings "
            f"across {result.get('distributors_touched', 0)} distributors"
        ),
    )


@router.post(
    "/create-email-drafts-bulk",
    response_model=DataResponse[BulkEmailDraftJobStartResponse],
    summary="[DEPRECATED] Start bulk Outlook draft creation (sequential)",
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
)
def create_email_drafts_bulk(
    payload: BulkEmailDraftRequest,
    current: RequireAdmin,
) -> DataResponse[BulkEmailDraftJobStartResponse]:
    """
    Start a background job that creates one Outlook draft per distributor.

    Processing is **sequential** (Excel → Graph draft → attach) to avoid Graph
    thundering herds. Poll ``GET .../create-email-drafts-bulk/{job_id}``.
    """
    job = bulk_email_draft_service.start_bulk_email_drafts(
        distributor_ids=payload.distributor_ids,
        reporting_quarter=payload.reporting_quarter,
        actor=current.name,
    )
    return DataResponse(
        data=BulkEmailDraftJobStartResponse(
            job_id=job.job_id,
            status=job.status,
            total=job.total,
            reporting_quarter=job.reporting_quarter,
        ),
        message="Bulk draft creation started. Poll the job status endpoint for progress.",
    )


@router.get(
    "/create-email-drafts-bulk/{job_id}",
    response_model=DataResponse[BulkEmailDraftJobStatusResponse],
    summary="[DEPRECATED] Poll bulk Outlook draft job status",
    deprecated=True,
)
def get_email_drafts_bulk_status(
    job_id: str,
    _: RequireAdmin,
) -> DataResponse[BulkEmailDraftJobStatusResponse]:
    """Return live progress / final results for a bulk draft job."""
    job = bulk_email_draft_service.get_job(job_id)
    if job is None:
        raise NotFoundError("Bulk draft job not found")
    return DataResponse(data=BulkEmailDraftJobStatusResponse.model_validate(job.to_dict()))


@router.get(
    "/{distributor_id}/customers",
    response_model=DataResponse[List[str]],
    summary="Mapped customers for distributor",
)
def list_distributor_customers(
    distributor_id: int,
    service: DistributorServiceDep,
    _: RequireUser,
) -> DataResponse[List[str]]:
    """Return active customer names learned for this distributor only."""
    return DataResponse(data=service.list_customers(distributor_id))


@router.post(
    "/{distributor_id}/create-email-draft",
    response_model=DataResponse[EmailDraftResponse],
    summary="[DEPRECATED] Create Outlook draft with distributor-specific Excel",
    deprecated=True,
)
@router.post(
    "/{distributor_id}/generate-quarterly-package",
    response_model=DataResponse[EmailDraftResponse],
    summary="[DEPRECATED] Create Outlook draft (legacy path alias)",
    include_in_schema=False,
    deprecated=True,
)
def create_email_draft(
    distributor_id: int,
    payload: QuarterlyPackageRequest,
    master: MasterDataServiceDep,
    current: RequireAdmin,
) -> DataResponse[EmailDraftResponse]:
    """
    Generate the same distributor-specific Excel as Master Data, then create a
    Microsoft Graph **draft** in GRAPH_MAILBOX (not sent).
    """
    result = master.create_email_draft(
        distributor_id=distributor_id,
        reporting_quarter=payload.reporting_quarter,
        actor=current.name,
    )
    return DataResponse(data=result, message=result.message)


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
    return DataResponse(data=_to_response(service, item))


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
    return DataResponse(
        data=_to_response(service, item), message="Distributor created"
    )


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
    return DataResponse(
        data=_to_response(service, item), message="Distributor updated"
    )


@router.delete(
    "/{distributor_id}",
    response_model=MessageResponse,
    summary="Delete distributor",
)
def delete_distributor(
    distributor_id: int,
    service: DistributorServiceDep,
    current: RequireAdmin,
    hard: bool = Query(
        True,
        description="If true, soft-delete distributor and cascade reports/sales",
    ),
) -> MessageResponse:
    """Delete distributor (default hard/cascade). Pass hard=false to only deactivate."""
    if hard:
        service.delete_distributor(distributor_id, actor=current.name)
        return MessageResponse(message=f"Distributor {distributor_id} deleted")
    service.deactivate_distributor(distributor_id, actor=current.name)
    return MessageResponse(message=f"Distributor {distributor_id} deactivated")
