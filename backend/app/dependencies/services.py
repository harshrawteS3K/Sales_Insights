"""Service provider dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.audit_service import AuditService
from app.services.consolidated_data_service import ConsolidatedDataService
from app.services.dashboard_service import DashboardService
from app.services.distributor_service import DistributorService
from app.services.master_data_service import MasterDataService
from app.services.outlook_sync_service import OutlookSyncService
from app.services.report_service import ReportService
from app.services.auth_service import AuthService
from app.services.user_management_service import UserManagementService
from app.services.user_service import UserService


def get_user_service(db: Annotated[Session, Depends(get_db)]) -> UserService:
    return UserService(db)


def get_user_management_service(db: Annotated[Session, Depends(get_db)]) -> UserManagementService:
    return UserManagementService(db)


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    return AuthService(db)


def get_distributor_service(db: Annotated[Session, Depends(get_db)]) -> DistributorService:
    return DistributorService(db)


def get_report_service(db: Annotated[Session, Depends(get_db)]) -> ReportService:
    return ReportService(db)


def get_consolidated_data_service(db: Annotated[Session, Depends(get_db)]) -> ConsolidatedDataService:
    return ConsolidatedDataService(db)


def get_audit_service(db: Annotated[Session, Depends(get_db)]) -> AuditService:
    return AuditService(db)


def get_dashboard_service(db: Annotated[Session, Depends(get_db)]) -> DashboardService:
    return DashboardService(db)


def get_master_data_service(db: Annotated[Session, Depends(get_db)]) -> MasterDataService:
    return MasterDataService(db)


def get_outlook_sync_service(db: Annotated[Session, Depends(get_db)]) -> OutlookSyncService:
    return OutlookSyncService(db)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
UserManagementServiceDep = Annotated[UserManagementService, Depends(get_user_management_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
DistributorServiceDep = Annotated[DistributorService, Depends(get_distributor_service)]
ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
ConsolidatedDataServiceDep = Annotated[ConsolidatedDataService, Depends(get_consolidated_data_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
MasterDataServiceDep = Annotated[MasterDataService, Depends(get_master_data_service)]
OutlookSyncServiceDep = Annotated[OutlookSyncService, Depends(get_outlook_sync_service)]
