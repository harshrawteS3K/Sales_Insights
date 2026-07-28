"""Dashboard endpoints."""

from fastapi import APIRouter

from app.dependencies.rbac import RequireUser
from app.dependencies.services import DashboardServiceDep
from app.schemas.common import DataResponse
from app.schemas.dashboard import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DataResponse[DashboardSummary], summary="Dashboard summary")
def dashboard_summary(
    service: DashboardServiceDep,
    _: RequireUser,
) -> DataResponse[DashboardSummary]:
    """Return aggregated dashboard KPIs and counts."""
    return DataResponse(data=service.summary())
