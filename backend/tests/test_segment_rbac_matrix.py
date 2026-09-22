"""Unit and API tests for Segment-wise RBAC and Segment Permission Matrix."""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.main import app
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.user_segment_repository import UserSegmentRepository
from app.services.user_management_service import UserManagementService


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:6]}"


def test_user_segment_repository_assignment(db: Session):
    user_repo = UserRepository(db)
    username = _uid("anup_test")
    user = User(
        username=username,
        email=f"{username}@apcotex.com",
        full_name="Anup Test",
        role="user",
        is_active=True,
    )
    user = user_repo.create(user)

    seg_repo = UserSegmentRepository(db)
    assigned = seg_repo.assign_segments_to_user(user.id, ["Construction", "Paper"])
    assert assigned == ["Construction", "Paper"]

    user_segs = seg_repo.list_segments_for_user(user.id)
    assert "Construction" in user_segs
    assert "Paper" in user_segs
    assert "Rubber" not in user_segs

    # Toggle Rubber ON
    updated = seg_repo.toggle_user_segment(user.id, "Rubber", True)
    assert "Rubber" in updated

    # Toggle Rubber OFF
    updated2 = seg_repo.toggle_user_segment(user.id, "Rubber", False)
    assert "Rubber" not in updated2


def test_segment_permission_matrix_endpoint(client: TestClient):
    # Admin headers
    headers = {"X-User-Role": "admin", "X-User-Name": "admin"}
    response = client.get("/api/v1/users/matrix", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "segments" in data
    assert "Paper" in data["segments"]
    assert "Construction" in data["segments"]
    assert isinstance(data["rows"], list)


def test_toggle_matrix_cell_endpoint(client: TestClient, db: Session):
    user_repo = UserRepository(db)
    username = _uid("matrix_user")
    user = User(
        username=username,
        email=f"{username}@apcotex.com",
        full_name="Matrix Test User",
        role="user",
        is_active=True,
    )
    user = user_repo.create(user)
    db.commit()

    headers = {"X-User-Role": "admin", "X-User-Name": "admin"}
    # Toggle Construction ON
    res = client.put(
        "/api/v1/users/matrix",
        json={"user_id": user.id, "segment": "Construction", "enabled": True},
        headers=headers,
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert "Construction" in res_data["data"]["assigned"]

    # Toggle Construction OFF
    res2 = client.put(
        "/api/v1/users/matrix",
        json={"user_id": user.id, "segment": "Construction", "enabled": False},
        headers=headers,
    )
    assert res2.status_code == 200
    assert "Construction" not in res2.json()["data"]["assigned"]
