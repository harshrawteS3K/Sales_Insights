"""Authentication endpoints."""

from fastapi import APIRouter

from app.dependencies.services import AuthServiceDep
from app.schemas.user import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse, summary="Login (DB users or Super Admin)")
def login(payload: LoginRequest, service: AuthServiceDep) -> LoginResponse:
    """
    Authenticate against database users first; if not found, compare against
    SUPER_ADMIN_USERNAME / SUPER_ADMIN_PASSWORD from the environment.

    Super Admin is never stored in the database.
    """
    data = service.login(payload.username, payload.password)
    return LoginResponse(data=data)
