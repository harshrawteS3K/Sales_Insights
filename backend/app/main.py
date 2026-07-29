"""
APCOTEX Sales Insights — FastAPI application entrypoint.

Run:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1.router import api_router
from app.constants import API_DESCRIPTION, API_TITLE, API_VERSION, OPENAPI_TAGS
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.database.session import check_database_connection
from app.exceptions import (
    AppException,
    app_exception_handler,
    integrity_error_handler,
    sqlalchemy_error_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware.request_logging import RequestLoggingMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown lifecycle."""
    setup_logging()
    settings.ensure_directories()
    logger.info(
        "Starting {} v{} | env={} | host={}:{}",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.app_host,
        settings.app_port,
    )
    if check_database_connection():
        logger.info("Database connectivity verified")
    else:
        logger.error("Database is unreachable at startup")

    auth_mode = (settings.auth_mode or "headers").strip().lower()
    logger.info(
        "Auth configuration | AUTH_MODE={} | production={} | trusted_secret_set={} | jwt_secret_set={}",
        auth_mode,
        settings.is_production,
        bool((settings.auth_trusted_secret or "").strip()),
        bool((settings.auth_jwt_secret or "").strip()),
    )
    if settings.is_production and auth_mode in {"headers", "header", "dev"}:
        logger.warning(
            "SECURITY: APP_ENV=production with AUTH_MODE=headers. "
            "Deploy only behind APCOTEX corporate network / VPN, or set "
            "AUTH_MODE=trusted_headers (with AUTH_TRUSTED_SECRET) or AUTH_MODE=jwt."
        )
    if settings.is_production and auth_mode == "trusted_headers" and not (
        settings.auth_trusted_secret or ""
    ).strip():
        logger.error(
            "SECURITY: AUTH_MODE=trusted_headers in production requires AUTH_TRUSTED_SECRET"
        )

    yield
    logger.info("Shutting down {}", settings.app_name)


def create_app() -> FastAPI:
    """Application factory."""
    application = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version=API_VERSION,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.debug = settings.debug

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestLoggingMiddleware)

    application.add_exception_handler(AppException, app_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(IntegrityError, integrity_error_handler)
    application.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    # Frontend Phase-2 contract uses /api/* ; also expose versioned /api/v1/*
    application.include_router(api_router, prefix="/api")
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/", tags=["Health"], include_in_schema=False)
    def root() -> dict:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/api/health",
        }

    return application


app = create_app()
