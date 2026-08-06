"""Master data endpoints — Phase 2 paths + legacy /master-data routes."""

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.dependencies.rbac import RequireAdmin, RequireUser
from app.dependencies.services import MasterDataServiceDep
from app.schemas.dashboard import (
    CustomerMasterListResponse,
    CustomerMasterResponse,
    MasterDataUploadResponse,
    ProductMasterListResponse,
    ProductMasterResponse,
    TemplateGenerateResponse,
)

router = APIRouter(tags=["Master Data"])


# ---------------------------------------------------------------------------
# Phase 2 canonical routes
# ---------------------------------------------------------------------------


@router.post(
    "/customer-master/upload",
    response_model=MasterDataUploadResponse,
    summary="Upload Customer Master Excel (replace)",
)
async def upload_customer_master(
    service: MasterDataServiceDep,
    current: RequireAdmin,
    file: UploadFile = File(..., description="Customer Master Excel (.xlsx)"),
) -> MasterDataUploadResponse:
    """Replace active Customer Master with CUSTOMER NAME values from Excel."""
    return await service.upload_customer_master(file, actor=current.name)


@router.post(
    "/product-master/upload",
    response_model=MasterDataUploadResponse,
    summary="Upload Product Master Excel (replace)",
)
async def upload_product_master(
    service: MasterDataServiceDep,
    current: RequireAdmin,
    file: UploadFile = File(..., description="Product Master Excel (.xlsx)"),
) -> MasterDataUploadResponse:
    """Replace active Product Master with Industry Type + Product Code rows."""
    return await service.upload_product_master(file, actor=current.name)


@router.post(
    "/template/generate",
    response_model=TemplateGenerateResponse,
    summary="Generate official distributor template",
)
def generate_template(
    service: MasterDataServiceDep,
    current: RequireAdmin,
) -> TemplateGenerateResponse:
    """Generate template with Customer / Product dropdowns from master data."""
    return service.generate_template(actor=current.name)


@router.get(
    "/template/download",
    summary="Download generated distributor template",
    response_class=FileResponse,
)
def download_template(
    service: MasterDataServiceDep,
    current: RequireAdmin,
) -> FileResponse:
    """Download the latest generated official distributor Excel template."""
    path, filename = service.resolve_template_download()
    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content_disposition_type="attachment",
    )


# ---------------------------------------------------------------------------
# Legacy /master-data routes (kept for compatibility)
# ---------------------------------------------------------------------------


@router.get(
    "/master-data/customers",
    response_model=CustomerMasterListResponse,
    summary="List customer master",
)
def list_customers(
    service: MasterDataServiceDep,
    _: RequireUser,
) -> CustomerMasterListResponse:
    rows = service.list_customers()
    return CustomerMasterListResponse(
        data=[CustomerMasterResponse.model_validate(r) for r in rows],
        total=service.count_customers(),
    )


@router.get(
    "/master-data/products",
    response_model=ProductMasterListResponse,
    summary="List product master",
)
def list_products(
    service: MasterDataServiceDep,
    _: RequireUser,
) -> ProductMasterListResponse:
    rows = service.list_products()
    return ProductMasterListResponse(
        data=[ProductMasterResponse.model_validate(r) for r in rows],
        total=service.count_products(),
    )


@router.post(
    "/master-data/customers/upload",
    response_model=MasterDataUploadResponse,
    summary="Upload customer master Excel (legacy)",
)
async def upload_customers_legacy(
    service: MasterDataServiceDep,
    current: RequireAdmin,
    file: UploadFile = File(...),
) -> MasterDataUploadResponse:
    return await service.upload_customer_master(file, actor=current.name)


@router.post(
    "/master-data/products/upload",
    response_model=MasterDataUploadResponse,
    summary="Upload product master Excel (legacy)",
)
async def upload_products_legacy(
    service: MasterDataServiceDep,
    current: RequireAdmin,
    file: UploadFile = File(...),
) -> MasterDataUploadResponse:
    return await service.upload_product_master(file, actor=current.name)


@router.get(
    "/master-data/templates/distributor",
    summary="Download distributor Excel template (legacy)",
    response_class=FileResponse,
)
def download_distributor_template_legacy(
    service: MasterDataServiceDep,
    current: RequireAdmin,
) -> FileResponse:
    result = service.generate_template(actor=current.name)
    path, filename = service.resolve_template_download(preferred_name=result.file_name)
    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
