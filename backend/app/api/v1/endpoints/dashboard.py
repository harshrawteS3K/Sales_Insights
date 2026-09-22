"""Dashboard endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.rbac import (
    RequireUser,
    distributor_companies_scope_for_user,
    segment_scope_for_user,
)
from app.dependencies.services import DashboardServiceDep
from app.schemas.common import DataResponse
from app.schemas.dashboard import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DataResponse[DashboardSummary], summary="Dashboard summary")
def dashboard_summary(
    service: DashboardServiceDep,
    current: RequireUser,
    db: Session = Depends(get_db),
) -> DataResponse[DashboardSummary]:
    """Return aggregated dashboard KPIs and counts."""
    allowed_segments = segment_scope_for_user(current, db)
    allowed_companies = distributor_companies_scope_for_user(current, db)
    return DataResponse(
        data=service.summary(
            allowed_segments=allowed_segments,
            allowed_companies=allowed_companies,
        )
    )
