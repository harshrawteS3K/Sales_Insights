"""ERP Excel parse + approve-import endpoints."""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, UploadFile

from app.dependencies.rbac import RequireAdmin, RequireUser
from app.database.session import get_db
from app.enums import UserRole
from app.services.segment_access_service import SegmentAccessService
from app.erp_parser import ERPParserService
from app.exceptions import ExcelProcessingError, ForbiddenError, ValidationAppError
from app.schemas.common import DataResponse, MessageResponse
from app.schemas.erp_parse import (
    ERPEmailPreviewRequest,
    ERPImportRequest,
    ERPImportResponse,
    ERPParsePreviewResponse,
)
from app.services.erp_ingest_service import ERPIngestService
from app.utils.files import get_upload_subdir, save_upload_file
from fastapi import Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/erp", tags=["ERP Parser"])


def _erp_service(db: Session = Depends(get_db)) -> ERPIngestService:
    return ERPIngestService(db)


def _resolve_user_email(current: RequireUser, db: Session) -> Optional[str]:
    """Prefer RBAC header email, then DB user.email."""
    email = (current.email or "").strip() or None
    if email:
        return email
    if current.user_id:
        from app.repositories.user_repository import UserRepository

        row = UserRepository(db).get_by_id(current.user_id)
        if row and (row.email or "").strip():
            return row.email.strip()
    return None


def _ensure_email_access(
    current: RequireUser,
    db: Session,
    email,
    *,
    check_segment: bool = True,
) -> None:
    """
    Admin: unrestricted.
    Sales Owner: must own the email (FROM == persona email) and have segment access.
    """
    role_val = current.role.value if hasattr(current.role, "value") else str(current.role)
    if role_val in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
        return

    user_email = (_resolve_user_email(current, db) or "").strip().lower()
    sender = (getattr(email, "sender_email", None) or "").strip().lower()
    if not user_email or not sender or user_email != sender:
        raise ForbiddenError(
            "You can only preview/import emails sent from your registered persona email.",
            details={
                "email_id": getattr(email, "id", None),
                "sender_email": sender or None,
                "your_email": user_email or None,
            },
        )

    if check_segment:
        SegmentAccessService(db).require_segment_access(
            current, getattr(email, "parsed_segment", None)
        )


@router.post(
    "/parse-preview",
    response_model=DataResponse[ERPParsePreviewResponse],
    summary="Preview ERP Excel parse (no import)",
)
async def parse_erp_preview(
    current: RequireAdmin,
    file: UploadFile = File(
        ...,
        description="multipart/form-data field 'file'; ERP Excel (.xlsx or .xlsm)",
    ),
) -> DataResponse[ERPParsePreviewResponse]:
    """Detect sheet/headers, map columns, extract rows. Does not import."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm", ".xls")):
        raise ValidationAppError("Only .xlsx, .xlsm, and .xls files are accepted")

    path = await save_upload_file(file, get_upload_subdir("erp_preview"))
    try:
        preview = ERPParserService().preview(Path(path))
        preview["workbook_name"] = file.filename
    except ExcelProcessingError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExcelProcessingError(f"ERP parse failed: {exc}") from exc

    return DataResponse(
        data=ERPParsePreviewResponse.model_validate(preview),
        message="ERP parse preview generated (not imported)",
    )


@router.post(
    "/emails/{email_id}/preview",
    response_model=DataResponse[ERPParsePreviewResponse],
    summary="Preview ERP Excel attached to an email",
)
def preview_email_attachment(
    email_id: int,
    current: RequireUser,
    payload: Optional[ERPEmailPreviewRequest] = None,
    service: ERPIngestService = Depends(_erp_service),
    db: Session = Depends(get_db),
) -> DataResponse[ERPParsePreviewResponse]:
    """Parse email attachment; optional mapping override recomputes rows."""
    email = service.emails.get_or_raise(email_id)
    # Ownership only here — subject/segment validated inside preview_email
    _ensure_email_access(current, db, email, check_segment=False)

    mapping = payload.mapping if payload else None
    fiscal_year_start = payload.fiscal_year_start if payload else None
    # Convert pydantic mapping items to plain dicts
    if mapping is not None and not isinstance(mapping, dict):
        mapping = [m.model_dump() if hasattr(m, "model_dump") else m for m in mapping]
    preview = service.preview_email(
        email_id,
        actor=current.name,
        mapping_override=mapping,
        fiscal_year_start=fiscal_year_start,
    )
    return DataResponse(
        data=ERPParsePreviewResponse.model_validate(preview),
        message="ERP email preview ready (not imported)",
    )


@router.post(
    "/import",
    response_model=DataResponse[ERPImportResponse],
    summary="Approve and import ERP rows",
)
def import_erp_rows(
    payload: ERPImportRequest,
    current: RequireUser,
    service: ERPIngestService = Depends(_erp_service),
    db: Session = Depends(get_db),
) -> DataResponse[ERPImportResponse]:
    """Import approved preview rows into Consolidated Data."""
    email = service.emails.get_or_raise(payload.email_id)
    _ensure_email_access(current, db, email, check_segment=True)
    mapping: Any = payload.mapping
    if mapping is not None and not isinstance(mapping, dict):
        mapping = [m.model_dump() if hasattr(m, "model_dump") else m for m in mapping]
    rows = None
    if payload.rows:
        rows = [r.model_dump() for r in payload.rows]
    result = service.import_approved(
        email_id=payload.email_id,
        distributor_id=payload.distributor_id,
        reporting_quarter=payload.reporting_quarter,
        actor=current.name,
        mapping=mapping,
        rows=rows,
        fiscal_year_start=payload.fiscal_year_start,
    )
    return DataResponse(
        data=ERPImportResponse.model_validate(result),
        message=f"Imported {result['records_inserted']} sales rows",
    )


@router.post(
    "/emails/{email_id}/skip",
    response_model=MessageResponse,
    summary="Skip an ERP email",
)
def skip_erp_email(
    email_id: int,
    current: RequireUser,
    service: ERPIngestService = Depends(_erp_service),
    db: Session = Depends(get_db),
) -> MessageResponse:
    email = service.emails.get_or_raise(email_id)
    _ensure_email_access(current, db, email, check_segment=False)
    service.skip_email(email_id, actor=current.name)
    return MessageResponse(message=f"Email {email_id} skipped")
