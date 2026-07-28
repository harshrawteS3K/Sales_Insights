"""Health check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.database.session import check_database_connection
from app.schemas.dashboard import HealthProbeResponse, HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health_check() -> HealthResponse:
    """Return service and database health status."""
    db_ok = check_database_connection()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database="up" if db_ok else "down",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/health/live", response_model=HealthProbeResponse, summary="Liveness probe")
def liveness() -> HealthProbeResponse:
    """Liveness probe."""
    return HealthProbeResponse(status="alive")


@router.get("/health/ready", response_model=HealthProbeResponse, summary="Readiness probe")
def readiness() -> HealthProbeResponse:
    """Readiness probe."""
    db_ok = check_database_connection()
    return HealthProbeResponse(
        status="ready" if db_ok else "not_ready",
        database="up" if db_ok else "down",
    )
