"""Authentication endpoints."""

from fastapi import APIRouter, Request, Response

from app.dependencies.services import AuthServiceDep
from app.schemas.user import LoginRequest, LoginResponse
from app.services.auth_service import SESSION_COOKIE_NAME, SESSION_TTL_HOURS

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse, summary="Login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> LoginResponse:
    """Validate username and password, then set the server session cookie."""
    data, token = service.login(payload.username, payload.password)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return LoginResponse(data=data)
