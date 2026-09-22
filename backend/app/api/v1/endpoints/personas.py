"""Persona management & bulk employee import endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.rbac import RequireAdmin
from app.exceptions import ValidationAppError
from app.schemas.common import DataResponse, MessageResponse
from app.services.bulk_persona_import_service import BulkPersonaImportService
from app.utils.files import get_upload_subdir, save_upload_file

router = APIRouter(prefix="/personas", tags=["Persona Management"])


@router.post(
    "/bulk-import/preview",
    summary="Preview bulk employee-distributor mapping Excel",
    tags=["Persona Management"],
)
async def preview_bulk_import(
    _: RequireAdmin,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DataResponse[dict]:
    """Parse uploaded Excel and return a preview summary before confirming import."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise ValidationAppError("Only Excel files (.xlsx or .xlsm) are supported for bulk import")

    tmp_dir = get_upload_subdir("temp_imports")
    saved_path = await save_upload_file(file, tmp_dir)

    try:
        service = BulkPersonaImportService(db)
        result = service.preview_import(saved_path)
        return DataResponse(data=result, message="Excel parsed successfully")
    finally:
        if saved_path.exists():
            try:
                saved_path.unlink()
            except Exception:
                pass


@router.post(
    "/bulk-import",
    summary="Execute bulk employee persona and distributor mapping import",
    tags=["Persona Management"],
)
async def execute_bulk_import(
    current: RequireAdmin,
    file: UploadFile = File(...),
    replace_existing: bool = Form(True),
    db: Session = Depends(get_db),
) -> DataResponse[dict]:
    """Execute bulk import: creates missing users and updates distributor/segment assignments."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise ValidationAppError("Only Excel files (.xlsx or .xlsm) are supported for bulk import")

    tmp_dir = get_upload_subdir("imports")
    saved_path = await save_upload_file(file, tmp_dir)

    try:
        service = BulkPersonaImportService(db)
        result = service.execute_import(
            saved_path,
            replace_existing=replace_existing,
            actor=current.name,
            assigned_by=current.user_id,
        )
        return DataResponse(data=result, message=result.get("message", "Bulk import successful"))
    finally:
        if saved_path.exists():
            try:
                saved_path.unlink()
            except Exception:
                pass


@router.get(
    "/sample-format",
    summary="Download sample format Excel for bulk employee import",
    tags=["Persona Management"],
)
def download_sample_format(
    _: RequireAdmin,
) -> FileResponse:
    """Download template Excel with required headers ('Second Party', 'Owner', 'Segment')."""
    path = BulkPersonaImportService.generate_sample_excel()
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )
