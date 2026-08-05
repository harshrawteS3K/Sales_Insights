"""User service — re-exports UserManagementService for DI compatibility."""

from app.services.user_management_service import UserManagementService, UserService

__all__ = ["UserManagementService", "UserService"]
