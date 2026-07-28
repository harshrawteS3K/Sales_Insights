"""Master data endpoints."""

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.constants import DISTRIBUTOR_TEMPLATE_FILENAME
from app.dependencies.rbac import RequireAdmin, RequireUser
from app.dependencies.services import MasterDataServiceDep
from app.schemas.dashboard import (
    CustomerMasterListResponse,
    CustomerMasterResponse,
    MasterDataUploadResponse,
    ProductMasterListResponse,
    ProductMasterResponse,
)

router = APIRouter(prefix="/master-data", tags=["Master Data"])


@router.get(
    "/customers",
    response_model=CustomerMasterListResponse,
    summary="List customer master",
)
def list_customers(
    service: MasterDataServiceDep,
    _: RequireUser,
) -> CustomerMasterListResponse:
    """List customer master rows."""
    rows = service.list_customers()
    return CustomerMasterListResponse(
        data=[CustomerMasterResponse.model_validate(r) for r in rows],
        total=service.count_customers(),
    )


@router.get(
    "/products",
    response_model=ProductMasterListResponse,
    summary="List product master",
)
def list_products(
    service: MasterDataServiceDep,
    _: RequireUser,
) -> ProductMasterListResponse:
    """List product master rows."""
    rows = service.list_products()
    return ProductMasterListResponse(
        data=[ProductMasterResponse.model_validate(r) for r in rows],
        total=service.count_products(),
    )


@router.post(
    "/customers/upload",
    response_model=MasterDataUploadResponse,
    summary="Upload customer master Excel",
)
async def upload_customers(
    service: MasterDataServiceDep,
    current: RequireAdmin,
    file: UploadFile = File(..., description="Customer master Excel (.xlsx or .xlsm)"),
) -> MasterDataUploadResponse:
    """Admin upload of customer master Excel (.xlsx or .xlsm)."""
    return await service.upload_customer_master(file, actor=current.name)


@router.post(
    "/products/upload",
    response_model=MasterDataUploadResponse,
    summary="Upload product master Excel",
)
async def upload_products(
    service: MasterDataServiceDep,
    current: RequireAdmin,
    file: UploadFile = File(..., description="Product master Excel (.xlsx or .xlsm)"),
) -> MasterDataUploadResponse:
    """Admin upload of product master Excel (.xlsx or .xlsm)."""
    return await service.upload_product_master(file, actor=current.name)


@router.get(
    "/templates/distributor",
    summary="Download distributor Excel template",
    response_class=FileResponse,
)
def download_distributor_template(
    service: MasterDataServiceDep,
    current: RequireAdmin,
) -> FileResponse:
    """Generate and download distributor sales template with dropdowns (Admin)."""
    path = service.generate_distributor_template(actor=current.name)
    return FileResponse(
        path=str(path),
        filename=DISTRIBUTOR_TEMPLATE_FILENAME,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
