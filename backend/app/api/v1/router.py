"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin_header_dictionary,
    analytics,
    audit,
    auth,
    consolidated_data,
    dashboard,
    distributors,
    erp,
    health,
    master_data,
    outlook,
    personas,
    reports,
    settings,
    users,
    visualizations,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(personas.router)
api_router.include_router(distributors.router)
api_router.include_router(reports.router)
api_router.include_router(dashboard.router)
api_router.include_router(outlook.router)
api_router.include_router(master_data.router)  # deprecated — kept for compatibility
api_router.include_router(erp.router)
api_router.include_router(admin_header_dictionary.router)
api_router.include_router(audit.router)
api_router.include_router(consolidated_data.router)
api_router.include_router(visualizations.router)
api_router.include_router(analytics.router)
api_router.include_router(settings.router)
