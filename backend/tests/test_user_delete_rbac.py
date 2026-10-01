"""Super Admin > Admin > Sales Owner rules for deleting and managing users."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import users as users_endpoints
from app.database.session import get_db
from app.dependencies.rbac import RequestUser, get_current_user
from app.dependencies.services import get_user_service
from app.enums import UserRole
from app.exceptions import AppException, ForbiddenError, app_exception_handler
from app.schemas.user import PasswordChange, StatusUpdate
from app.services.user_management_service import UserService

SUPER = UserRole.SUPER_ADMIN.value
ADMIN = UserRole.ADMIN.value
USER = UserRole.USER.value


def _user(uid: int, role: str, username: str = "someone") -> SimpleNamespace:
    return SimpleNamespace(
        id=uid,
        username=username,
        full_name=f"User {uid}",
        role=role,
        is_active=True,
        is_deleted=False,
        email=f"{username}@apcotex.com",
        title=None,
        phone=None,
        department=None,
        notes=None,
        outlook_sync_permission="own",
        created_at=None,
        updated_at=None,
    )


def _service(target: SimpleNamespace) -> UserService:
    svc = UserService.__new__(UserService)
    svc.db = MagicMock()
    svc.db.execute.return_value.all.return_value = [(3, "REDACHEM VIETNAM COMPANY LIMITED")]
    svc.users = MagicMock()
    svc.users.get_or_raise.return_value = target

    def _soft_delete(u):
        u.is_deleted = True
        return u

    def _update(u, data):
        for key, value in data.items():
            setattr(u, key, value)
        return u

    svc.users.soft_delete.side_effect = _soft_delete
    svc.users.update.side_effect = _update
    svc.user_segments = MagicMock()
    svc.user_distributors = MagicMock()
    svc.audit = MagicMock()
    return svc


def test_super_admin_deletes_admin_and_removes_only_distributor_links():
    target = _user(11, ADMIN, "admin2")
    svc = _service(target)

    deleted = svc.delete_user(11, actor="Super Admin", actor_role=SUPER, actor_id=22)

    assert deleted.is_deleted is True
    assert deleted.is_active is False
    statements = [str(call.args[0]) for call in svc.db.execute.call_args_list]
    assert any("DELETE FROM user_distributors" in s for s in statements)
    assert any("UPDATE auth_sessions" in s for s in statements)
    assert not any("distributors " in s and s.startswith("DELETE FROM distributors") for s in statements)
    assert not any("sales_records" in s or "reports" in s for s in statements)

    meta = svc.audit.log.call_args.args[0].extra_metadata
    assert meta["deleted_user_id"] == 11
    assert meta["deleted_username"] == "admin2"
    assert meta["deleted_role"] == ADMIN
    assert meta["actor_user_id"] == 22
    assert meta["distributor_assignments"] == [
        {"distributor_id": 3, "distributor": "REDACHEM VIETNAM COMPANY LIMITED"}
    ]
    assert meta["deleted_at"]
    assert "password" not in str(meta).lower()


def test_admin_cannot_delete_admin():
    svc = _service(_user(11, ADMIN))
    with pytest.raises(ForbiddenError):
        svc.delete_user(11, actor="Admin", actor_role=ADMIN, actor_id=1)
    svc.users.soft_delete.assert_not_called()


def test_nobody_can_delete_super_admin():
    for role, actor_id in ((ADMIN, 1), (SUPER, 99)):
        svc = _service(_user(22, SUPER, "superadmin"))
        with pytest.raises(ForbiddenError):
            svc.delete_user(22, actor="x", actor_role=role, actor_id=actor_id)
        svc.users.soft_delete.assert_not_called()


def test_cannot_delete_own_account():
    svc = _service(_user(21, ADMIN))
    with pytest.raises(ForbiddenError):
        svc.delete_user(21, actor="Super Admin", actor_role=SUPER, actor_id=21)
    svc.users.soft_delete.assert_not_called()


def test_admin_can_still_delete_sales_owner():
    svc = _service(_user(5, USER))
    svc.delete_user(5, actor="Admin", actor_role=ADMIN, actor_id=1)
    svc.users.soft_delete.assert_called_once()


def test_admin_cannot_deactivate_or_reset_super_admin():
    svc = _service(_user(22, SUPER, "superadmin"))
    with pytest.raises(ForbiddenError):
        svc.set_status(22, StatusUpdate(is_active=False), actor="Admin", actor_role=ADMIN, actor_id=1)
    with pytest.raises(ForbiddenError):
        svc.change_password(
            22,
            PasswordChange(new_password="GoodPass1!", confirm_password="GoodPass1!"),
            actor="Admin",
            actor_role=ADMIN,
        )
    svc.users.update.assert_not_called()


def test_super_admin_cannot_deactivate_self_but_can_deactivate_admin():
    me = _service(_user(22, SUPER, "superadmin"))
    with pytest.raises(ForbiddenError):
        me.set_status(22, StatusUpdate(is_active=False), actor="SA", actor_role=SUPER, actor_id=22)

    other = _service(_user(11, ADMIN))
    updated = other.set_status(
        11, StatusUpdate(is_active=False), actor="SA", actor_role=SUPER, actor_id=22
    )
    assert updated.is_active is False


def _client(caller: RequestUser, target: SimpleNamespace) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.include_router(users_endpoints.router, prefix="/api")
    app.dependency_overrides[get_user_service] = lambda: _service(target)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_current_user] = lambda: caller
    return TestClient(app, raise_server_exceptions=False)


def test_delete_endpoint_statuses():
    superadmin = RequestUser(role=UserRole.SUPER_ADMIN, name="Super Admin", user_id=22)
    admin = RequestUser(role=UserRole.ADMIN, name="Admin", user_id=1)
    sales = RequestUser(role=UserRole.USER, name="Sales", user_id=5)

    assert _client(superadmin, _user(11, ADMIN)).delete("/api/users/11").status_code == 200
    assert _client(admin, _user(22, SUPER)).delete("/api/users/22").status_code == 403
    assert _client(admin, _user(11, ADMIN)).delete("/api/users/11").status_code == 403
    assert _client(superadmin, _user(22, SUPER)).delete("/api/users/22").status_code == 403
    assert _client(sales, _user(11, ADMIN)).delete("/api/users/11").status_code == 403
    assert (
        _client(admin, _user(22, SUPER))
        .put("/api/users/22/status", json={"is_active": False})
        .status_code
        == 403
    )
