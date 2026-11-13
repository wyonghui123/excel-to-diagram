# -*- coding: utf-8 -*-
"""B2-1 统一元数据端点测试

覆盖：
- /api/v2/meta/enums/<name>（permission_level / task_status / hierarchy_level / 未知）
- /api/v2/meta/permission-matrix-schema
- /api/v2/meta/permission-meta
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
def admin_headers(api_client):
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


class TestMetaEnums:
    def test_permission_level_enum(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/enums/permission_level", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        values = [item["value"] for item in body["data"]["items"]]
        assert values == ["none", "read", "write", "admin"]

    def test_task_status_enum_from_yaml(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/enums/task_status", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        items = body["data"]["items"]
        assert items, "task_status 枚举不能为空"
        assert all("value" in item and "label" in item for item in items)

    def test_hierarchy_level_enum(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/enums/hierarchy_level", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        items = body["data"]["items"]
        assert items, "hierarchy_level 枚举不能为空"
        assert {"value", "label", "level"} <= set(items[0].keys())

    def test_unknown_enum_is_fail_closed(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/enums/not_exists_enum", headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get("success") is False

    def test_permission_matrix_schema(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/permission-matrix-schema", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert set(data["group_actions_map"].keys()) == {"view", "edit", "manage"}
        assert data["resource_labels"]
        assert data["action_columns"]

    def test_permission_meta_alias(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/permission-meta", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        data = body.get("data") or {}
        data = data.get("data", data)
        assert data.get("resource_type_labels")
        assert data.get("action_labels")
        assert data.get("resource_action_matrix")