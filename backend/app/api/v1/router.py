"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    consolidated_data,
    dashboard,
    distributors,
    health,
    master_data,
    outlook,
    reports,
    users,
    visualizations,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(distributors.router)
api_router.include_router(reports.router)
api_router.include_router(dashboard.router)
api_router.include_router(outlook.router)
api_router.include_router(master_data.router)
api_router.include_router(audit.router)
api_router.include_router(consolidated_data.router)
api_router.include_router(visualizations.router)
