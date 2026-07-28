"""Application exception hierarchy and HTTP error payloads."""

from typing import Any, Optional

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """Base application exception with HTTP metadata."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "APP_ERROR",
        details: Optional[Any] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        super().__init__(message)


class NotFoundError(AppException):
    """Resource was not found."""

    def __init__(self, message: str = "Resource not found", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            details=details,
        )


class ConflictError(AppException):
    """Resource conflict (e.g. duplicate)."""

    def __init__(self, message: str = "Conflict", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            details=details,
        )


class ValidationAppError(AppException):
    """Domain validation failure."""

    def __init__(self, message: str = "Validation error", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class UnauthorizedError(AppException):
    """Caller is not authenticated / authorized for the action."""

    def __init__(self, message: str = "Unauthorized", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
            details=details,
        )


class ForbiddenError(AppException):
    """Caller lacks required role."""

    def __init__(self, message: str = "Forbidden", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
            details=details,
        )


class GraphAPIError(AppException):
    """Microsoft Graph API failure."""

    def __init__(self, message: str = "Graph API error", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="GRAPH_API_ERROR",
            details=details,
        )


class ExcelProcessingError(AppException):
    """Excel parse / validation failure."""

    def __init__(self, message: str = "Excel processing error", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="EXCEL_PROCESSING_ERROR",
            details=details,
        )


class DatabaseError(AppException):
    """Database operation failure."""

    def __init__(self, message: str = "Database error", details: Optional[Any] = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DATABASE_ERROR",
            details=details,
        )


def _error_body(
    *,
    message: str,
    error_code: str,
    details: Any = None,
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "details": details,
            "request_id": request_id,
        },
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle known application exceptions."""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "AppException | code={} | status={} | path={} | message={} | details={}",
        exc.error_code,
        exc.status_code,
        request.url.path,
        exc.message,
        exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            message=exc.message,
            error_code=exc.error_code,
            details=exc.details,
            request_id=request_id,
        ),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle FastAPI / Pydantic request validation errors."""
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "Validation error | path={} | errors={}",
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(
            message="Request validation failed",
            error_code="REQUEST_VALIDATION_ERROR",
            details=exc.errors(),
            request_id=request_id,
        ),
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Handle SQLAlchemy integrity / unique constraint violations."""
    request_id = getattr(request.state, "request_id", None)
    logger.error("IntegrityError | path={} | error={}", request.url.path, str(exc.orig))
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=_error_body(
            message="Database integrity constraint violated",
            error_code="INTEGRITY_ERROR",
            details=str(exc.orig) if exc.orig else str(exc),
            request_id=request_id,
        ),
    )


async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle generic SQLAlchemy errors."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("SQLAlchemyError | path={}", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            message="Database operation failed",
            error_code="DATABASE_ERROR",
            details=str(exc),
            request_id=request_id,
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unexpected exceptions."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled exception | path={} | type={}", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            message="Internal server error",
            error_code="INTERNAL_SERVER_ERROR",
            details=str(exc) if getattr(request.app.state, "debug", False) else None,
            request_id=request_id,
        ),
    )
