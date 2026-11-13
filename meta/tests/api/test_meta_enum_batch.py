# -*- coding: utf-8 -*-
"""T13-1 批量枚举端点测试

覆盖：
- GET /api/v2/meta/enums/batch
  - 缺 names 参数 → 空对象 {}
  - 未知 name 不返回 500（跳过）
  - color 只允许 success|warning|danger|info|primary，非法值被丢弃
"""

import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api_client():
    from meta.tests.conftest import get_shared_app

    return get_shared_app()[1]


@pytest.fixture(scope="module")
def admin_headers():
    from meta.services.auth_provider import UserInfo
    from meta.services.token_service import TokenService

    admin_user = UserInfo(
        user_id="1",
        username="admin",
        display_name="Admin",
        email="admin@test.com",
        roles=["admin"],
        permissions=["*"],
    )
    token, _ = TokenService.create_token(admin_user)
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


class TestMetaEnumBatch:
    def test_missing_names_returns_empty_object(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/enums/batch", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        assert body["data"] == {}

    def test_unknown_name_does_not_500(self, api_client, admin_headers):
        resp = api_client.get(
            "/api/v2/meta/enums/batch?names=permission_level,no_such_enum",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        assert "permission_level" in body["data"]
        assert "no_such_enum" not in body["data"]

    def test_invalid_color_filtered(self, api_client, admin_headers, monkeypatch):
        from meta.api import meta_enum_api

        monkeypatch.setattr(
            meta_enum_api,
            "resolve_enum",
            lambda name: [
                {"value": "a", "label": "A", "color": "success", "category": "c1"},
                {"value": "b", "label": "B", "color": "rainbow", "category": "c2"},
                {"value": "c", "label": "C"},
            ],
        )
        resp = api_client.get(
            "/api/v2/meta/enums/batch?names=fake_enum", headers=admin_headers
        )
        assert resp.status_code == 200
        items = resp.get_json()["data"]["fake_enum"]
        by_value = {item["value"]: item for item in items}
        assert by_value["a"]["color"] == "success"
        assert "color" not in by_value["b"]
        assert "color" not in by_value["c"]
        assert by_value["b"]["category"] == "c2"
        allowed = {"success", "warning", "danger", "info", "primary"}
        assert all(item.get("color") in allowed for item in items if "color" in item)