"""Super Admin identity management and authentication tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.endpoints import auth as auth_endpoints
from app.api.v1.endpoints import users as users_endpoints
from app.core.config import settings
from app.dependencies.rbac import RequestUser, require_roles
from app.dependencies.services import get_auth_service, get_user_service
from app.enums import UserRole
from app.exceptions import AppException, ForbiddenError, UnauthorizedError, ValidationAppError
from app.schemas.user import LoginUserData, UserCreate
from app.services.auth_service import AuthService
from app.utils.passwords import (
    hash_password,
    normalize_username,
    validate_password_strength,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("Str0ng!Pass")
    assert hashed != "Str0ng!Pass"
    assert verify_password("Str0ng!Pass", hashed)
    assert not verify_password("wrong", hashed)


def test_password_policy_rejects_weak():
    with pytest.raises(ValidationAppError):
        validate_password_strength("short")
    with pytest.raises(ValidationAppError):
        validate_password_strength("alllowercase1!")
    with pytest.raises(ValidationAppError):
        validate_password_strength("ALLUPPERCASE1!")
    with pytest.raises(ValidationAppError):
        validate_password_strength("NoDigits!!")
    with pytest.raises(ValidationAppError):
        validate_password_strength("NoSpecial1")
    validate_password_strength("GoodPass1!")


@pytest.mark.asyncio
async def test_require_roles_super_admin_passes_admin_gate():
    admin_gate = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)
    super_user = RequestUser(role=UserRole.SUPER_ADMIN, name="Super Admin")
    assert await admin_gate(super_user) is super_user

    user_only = require_roles(UserRole.USER)
    with pytest.raises(ForbiddenError):
        await user_only(super_user)


def test_auth_service_super_admin_from_env(monkeypatch):
    monkeypatch.setattr(settings, "super_admin_username", "superadmin")
    monkeypatch.setattr(settings, "super_admin_password", "SuPeR@dmin@123")

    users_repo = MagicMock()
    users_repo.get_by_username.return_value = None
    audit = MagicMock()

    service = AuthService.__new__(AuthService)
    service.db = MagicMock()
    service.users = users_repo
    service.audit = audit

    result = service.login("superadmin", "SuPeR@dmin@123")
    assert result.role == UserRole.SUPER_ADMIN.value
    assert result.user_id is None
    assert result.name == "Super Admin"
    audit.log.assert_called()


def test_auth_service_db_user_inactive_blocked(monkeypatch):
    monkeypatch.setattr(settings, "super_admin_username", "superadmin")
    monkeypatch.setattr(settings, "super_admin_password", "SuPeR@dmin@123")

    inactive = SimpleNamespace(
        id=3,
        username="bob",
        full_name="Bob",
        title="Analyst",
        role=UserRole.USER.value,
        is_active=False,
        password_hash=hash_password("GoodPass1!"),
    )
    users_repo = MagicMock()
    users_repo.get_by_username.return_value = inactive
    audit = MagicMock()

    service = AuthService.__new__(AuthService)
    service.db = MagicMock()
    service.users = users_repo
    service.audit = audit

    with pytest.raises(UnauthorizedError):
        service.login("bob", "GoodPass1!")


def test_auth_service_db_user_before_super_admin(monkeypatch):
    """If a DB user matches the username, never fall through to Super Admin."""
    monkeypatch.setattr(settings, "super_admin_username", "admin")
    monkeypatch.setattr(settings, "super_admin_password", "SuPeR@dmin@123")

    db_user = SimpleNamespace(
        id=1,
        username="admin",
        full_name="Debabrata C",
        title="CMO",
        role=UserRole.ADMIN.value,
        is_active=True,
        password_hash=hash_password("admin123"),
    )
    users_repo = MagicMock()
    users_repo.get_by_username.return_value = db_user
    audit = MagicMock()

    service = AuthService.__new__(AuthService)
    service.db = MagicMock()
    service.users = users_repo
    service.audit = audit

    result = service.login("admin", "admin123")
    assert result.role == UserRole.ADMIN.value
    assert result.user_id == 1


def _app_with_handlers() -> FastAPI:
    from app.exceptions import app_exception_handler

    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    return app


def test_users_endpoints_require_admin():
    from app.database.session import get_db

    app = _app_with_handlers()
    app.include_router(users_endpoints.router, prefix="/api")

    class FakeUsers:
        db = MagicMock()

        def list_users(self, **kwargs):
            return []

        def count_users(self, **kwargs):
            return 0

    app.dependency_overrides[get_user_service] = lambda: FakeUsers()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    client = TestClient(app, raise_server_exceptions=False)

    res_admin = client.get("/api/users", headers={"X-User-Role": "admin", "X-User-Name": "Admin"})
    assert res_admin.status_code == 200

    res_user = client.get("/api/users", headers={"X-User-Role": "user", "X-User-Name": "User"})
    assert res_user.status_code == 403

    res_ok = client.get(
        "/api/users",
        headers={"X-User-Role": "super_admin", "X-User-Name": "Super Admin"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["total"] == 0


def test_login_endpoint():
    app = _app_with_handlers()
    app.include_router(auth_endpoints.router, prefix="/api")

    class FakeAuth:
        def login(self, username, password):
            if username == "superadmin" and password == "ok":
                return LoginUserData(
                    role="super_admin",
                    name="Super Admin",
                    title="Identity Administrator",
                    username="superadmin",
                    user_id=None,
                )
            raise UnauthorizedError("Invalid username or password")

    app.dependency_overrides[get_auth_service] = lambda: FakeAuth()
    client = TestClient(app, raise_server_exceptions=False)

    bad = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert bad.status_code == 401

    good = client.post("/api/auth/login", json={"username": "superadmin", "password": "ok"})
    assert good.status_code == 200
    assert good.json()["data"]["role"] == "super_admin"


def test_create_user_schema_blocks_super_admin_role():
    with pytest.raises(ValidationError):
        UserCreate(
            full_name="X",
            username="someone",
            password="GoodPass1!",
            role=UserRole.SUPER_ADMIN,
        )


def test_normalize_username():
    assert normalize_username("  Admin  ") == "admin"
