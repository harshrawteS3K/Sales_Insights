"""Super Admin–only product normalization skeleton."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.v1.endpoints import normalization as normalization_endpoints
from app.database.session import SessionLocal, get_db
from app.dependencies.rbac import RequestUser, get_current_user
from app.enums import UserRole
from app.exceptions import AppException, app_exception_handler
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.normalization import ProductMappingRow
from app.services.auth_service import AuthService
from app.utils.passwords import hash_password, verify_password

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
URL = "/api/normalization/product-mappings"


class _FakeNormalization:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def list_product_mappings(self, **kwargs):
        self.calls.append(kwargs)
        return PaginatedResponse[ProductMappingRow](
            data=[
                ProductMappingRow(
                    id=1,
                    distributor_id=7,
                    distributor_name="REDA",
                    original_product_name="Apcotex N 756 NBR",
                    normalized_product_name="APCOTEX N 756",
                )
            ],
            meta=PaginationMeta(page=1, page_size=50, total=1, total_pages=1),
        )


def _client(user: RequestUser | None) -> tuple[TestClient, _FakeNormalization]:
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.include_router(normalization_endpoints.router, prefix="/api")
    fake = _FakeNormalization()
    app.dependency_overrides[normalization_endpoints.get_normalization_service] = lambda: fake
    app.dependency_overrides[get_db] = lambda: MagicMock()
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False), fake


def test_superadmin_login_succeeds():
    row = SimpleNamespace(
        id=22,
        username="superadmin",
        full_name="Super Admin",
        title="Identity Administrator",
        role=UserRole.SUPER_ADMIN.value,
        email="superadmin@apcotex.com",
        is_active=True,
        password_hash=hash_password("SuPeR@dmin@123"),
        outlook_sync_permission="all",
    )
    service = AuthService.__new__(AuthService)
    service.db = MagicMock()
    service.users = MagicMock()
    service.users.get_by_username.return_value = row
    service.audit = MagicMock()

    data, token = service.login("superadmin", "SuPeR@dmin@123")
    assert data.role == UserRole.SUPER_ADMIN.value
    assert token


def test_superadmin_password_is_bcrypt_not_plaintext():
    hashed = hash_password("SuPeR@dmin@123")
    assert hashed != "SuPeR@dmin@123"
    assert hashed.startswith("$2")
    assert verify_password("SuPeR@dmin@123", hashed)
    assert not verify_password("superadmin", hashed)


def test_seeded_superadmin_row_is_single_and_hashed():
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(User).where(
                func.lower(User.username) == "superadmin",
                User.is_deleted.is_(False),
            )
        ).all()
    finally:
        db.close()
    if not rows:
        pytest.skip("superadmin is not seeded in this database")
    assert len(rows) == 1
    user = rows[0]
    assert user.role == UserRole.SUPER_ADMIN.value
    assert user.password_hash != "SuPeR@dmin@123"
    assert user.password_hash.startswith("$2")


def test_superadmin_can_list_mappings():
    client, fake = _client(RequestUser(role=UserRole.SUPER_ADMIN, name="Super Admin", user_id=22))
    res = client.get(URL, params={"distributor": "reda", "original_product": "756"})
    assert res.status_code == 200
    row = res.json()["data"][0]
    assert row["distributor_name"] == "REDA"
    assert row["original_product_name"] == "Apcotex N 756 NBR"
    assert row["normalized_product_name"] == "APCOTEX N 756"
    assert fake.calls[0]["distributor"] == "reda"
    assert fake.calls[0]["original_product"] == "756"


def test_admin_gets_403():
    client, fake = _client(RequestUser(role=UserRole.ADMIN, name="Admin", user_id=1))
    assert client.get(URL).status_code == 403
    assert fake.calls == []


def test_normal_user_gets_403():
    client, fake = _client(RequestUser(role=UserRole.USER, name="Sales", user_id=2))
    assert client.get(URL).status_code == 403
    assert fake.calls == []


def test_unauthenticated_gets_401_even_with_spoofed_role_header():
    client, fake = _client(None)
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers={"X-User-Role": "super_admin"}).status_code == 401
    assert fake.calls == []


def test_sidebar_shows_normalization_only_to_superadmin():
    sidebar = (FRONTEND_SRC / "components" / "layout" / "Sidebar.tsx").read_text(encoding="utf-8")
    item = next(line for line in sidebar.splitlines() if "'/normalization'" in line)
    assert "label: 'Normalization'" in item
    assert "superAdminOnly: true" in item
    assert "isSuperAdminRole(userRole)" in sidebar

    routes = (FRONTEND_SRC / "routes" / "index.tsx").read_text(encoding="utf-8")
    assert "userRole === 'super_admin'" in routes
    assert "path: 'normalization', Component: NormalizationPage" in routes


def test_normalization_page_has_required_columns():
    page = (FRONTEND_SRC / "pages" / "Normalization" / "NormalizationPage.tsx").read_text(
        encoding="utf-8"
    )
    assert (
        "NORMALIZATION_COLUMNS = ['Distributor', 'Original Product', 'Normalized Product']" in page
    )
    assert "isSuperAdminRole(userRole)" in page
    assert "NormalizationService.listProductMappings" in page
    assert "'All Distributors'" in page
    assert "You do not have permission to access Normalization." in page
    assert "Unable to load normalization mappings. Please check backend logs." in page
    # Empty state is only reached after the error branch.
    assert page.index(") : error ? (") < page.index("No product mappings yet.")


def test_real_mappings_listed_without_filters_and_global_rows_kept():
    from app.models.product_alias_mapping import ProductAliasMapping
    from app.services.normalization_service import NormalizationService

    db = SessionLocal()
    try:
        active = int(
            db.scalar(
                select(func.count())
                .select_from(ProductAliasMapping)
                .where(ProductAliasMapping.is_active.is_(True))
            )
            or 0
        )
        if not active:
            pytest.skip("no product mappings loaded in this database")
        service = NormalizationService(db)
        page = service.list_product_mappings(page=1, page_size=500)
        assert page.meta.total == active
        ids = [row.id for row in page.data]
        assert ids == sorted(ids)

        globals_only = int(
            db.scalar(
                select(func.count())
                .select_from(ProductAliasMapping)
                .where(
                    ProductAliasMapping.is_active.is_(True),
                    ProductAliasMapping.distributor_id.is_(None),
                )
            )
            or 0
        )
        filtered = service.list_product_mappings(distributor="no-such-distributor-xyz")
        assert filtered.meta.total == globals_only

        for original, normalized in (("7480", "INZAPOL BL 7480"), ("OPT 4815", "OPT LATEX 4815 CC")):
            hits = service.list_product_mappings(original_product=original).data
            pairs = {(r.original_product_name, r.normalized_product_name) for r in hits}
            if hits:
                assert (original, normalized) in pairs
    finally:
        db.rollback()
        db.close()


def test_listing_mappings_does_not_touch_sales_records():
    from app.services.normalization_service import NormalizationService

    fingerprint_sql = text(
        "SELECT count(*), coalesce(sum(quantity), 0), "
        "md5(coalesce(string_agg(id::text || '|' || product || '|' || quantity::text, ',' "
        "ORDER BY id), '')), max(updated_at) FROM sales_records"
    )
    db = SessionLocal()
    try:
        before = db.execute(fingerprint_sql).one()
        NormalizationService(db).list_product_mappings(page=1, page_size=10)
        NormalizationService(db).list_product_mappings(
            distributor="x", original_product="y", normalized_product="z"
        )
        db.rollback()
        after = db.execute(fingerprint_sql).one()
    finally:
        db.close()
    assert tuple(before) == tuple(after)
