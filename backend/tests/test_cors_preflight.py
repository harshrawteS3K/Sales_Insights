"""CORS preflight for login — local + UAT origins (no auth logic changes)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


@pytest.fixture()
def cors_client(monkeypatch: pytest.MonkeyPatch):
    """App with localhost + UAT-style origin in CORS_ORIGINS."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://10.0.3.213:5173",
    )
    from app.core import config as config_mod
    import app.main as main_mod

    config_mod.get_settings.cache_clear()
    fresh = config_mod.get_settings()
    monkeypatch.setattr(config_mod, "settings", fresh)
    monkeypatch.setattr(main_mod, "settings", fresh)

    app = main_mod.create_app()
    with TestClient(app) as client:
        yield client

    config_mod.get_settings.cache_clear()


def test_parse_cors_comma_separated_trims_and_skips_empty():
    from app.core.config import _parse_cors_value

    assert _parse_cors_value(" http://localhost:5173 , , http://10.0.3.213:5173 ") == [
        "http://localhost:5173",
        "http://10.0.3.213:5173",
    ]


def test_options_login_local_origin_ok(cors_client: TestClient):
    r = _preflight(cors_client, "http://localhost:5173")
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "POST" in (r.headers.get("access-control-allow-methods") or "")


def test_options_login_uat_origin_ok(cors_client: TestClient):
    r = _preflight(cors_client, "http://10.0.3.213:5173")
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://10.0.3.213:5173"


def test_options_login_unknown_origin_rejected(cors_client: TestClient):
    r = _preflight(cors_client, "http://evil.example:5173")
    assert r.status_code == 400
    assert "origin" in r.text.lower()


def test_create_app_middleware_order_cors_inner_logging_outer(monkeypatch: pytest.MonkeyPatch):
    """Last added middleware is outermost: RequestLogging → CORS → routers."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    from app.core import config as config_mod
    import app.main as main_mod

    config_mod.get_settings.cache_clear()
    fresh = config_mod.get_settings()
    monkeypatch.setattr(config_mod, "settings", fresh)
    monkeypatch.setattr(main_mod, "settings", fresh)

    app = main_mod.create_app()
    names = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in names
    assert "RequestLoggingMiddleware" in names
    # add_middleware prepends: index 0 = outermost. Expect RequestLogging → CORS → app.
    assert names[0] == "RequestLoggingMiddleware"
    assert names.index("CORSMiddleware") > 0
