"""Admin endpoints for ERP header synonym dictionary."""

from fastapi import APIRouter

from app.dependencies.rbac import RequireAdmin
from app.dependencies.services import AuditServiceDep
from app.enums import AuditAction
from app.erp_parser.header_dictionary import get_header_dictionary
from app.exceptions import ValidationAppError
from app.schemas.common import DataResponse
from app.schemas.audit import AuditTrailCreate
from app.schemas.header_dictionary import (
    HeaderDictionaryPayload,
    HeaderDictionaryUpdateMeta,
    HeaderDictionaryUpdateResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/header-dictionary",
    response_model=DataResponse[HeaderDictionaryPayload],
    summary="Get ERP header synonym dictionary",
)
def get_header_dictionary_api(
    _: RequireAdmin,
) -> DataResponse[HeaderDictionaryPayload]:
    data = get_header_dictionary().get_all()
    return DataResponse(
        data=HeaderDictionaryPayload.model_validate(data),
        message="ERP header dictionary",
    )


@router.put(
    "/header-dictionary",
    response_model=DataResponse[HeaderDictionaryUpdateResponse],
    summary="Update ERP header synonym dictionary",
)
def put_header_dictionary_api(
    payload: HeaderDictionaryPayload,
    current: RequireAdmin,
    audit: AuditServiceDep,
) -> DataResponse[HeaderDictionaryUpdateResponse]:
    dictionary = get_header_dictionary()
    try:
        new_data, added, removed = dictionary.update(payload.model_dump())
    except ValueError as exc:
        raise ValidationAppError(str(exc)) from exc
    except FileNotFoundError as exc:
        raise ValidationAppError(str(exc)) from exc

    added_flat = [f"{k}:{h}" for k, items in added.items() for h in items]
    removed_flat = [f"{k}:{h}" for k, items in removed.items() for h in items]

    audit.log(
        AuditTrailCreate(
            user_name=current.name,
            action=AuditAction.UPDATED,
            details=(
                "Header Dictionary Updated | "
                f"added={added_flat or ['(none)']} | "
                f"removed={removed_flat or ['(none)']}"
            ),
            entity_type="header_dictionary",
            entity_id="erp",
            module="Admin",
            status="Success",
            extra_metadata={
                "added": added,
                "removed": removed,
            },
        )
    )

    return DataResponse(
        data=HeaderDictionaryUpdateResponse(
            dictionary=HeaderDictionaryPayload.model_validate(new_data),
            changes=HeaderDictionaryUpdateMeta(added=added, removed=removed),
        ),
        message="Header dictionary saved",
    )
