"""Basic API smoke tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "app" in response.json()


def test_health_live() -> None:
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_openapi() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"]
