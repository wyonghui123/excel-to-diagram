# -*- coding: utf-8 -*-
"""B2-4 / B2-5 下沉接口测试

覆盖：
- POST /api/v2/bo/<object_type>/validate（字段策略校验下沉）
- GET  /api/v2/meta/selection-limit（选择上限后端唯一来源）
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


class TestBoValidate:
    def test_unknown_object_returns_404(self, api_client, admin_headers):
        resp = api_client.post(
            "/api/v2/bo/__not_exists__/validate",
            json={"data": {}},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_data_not_dict_returns_400(self, api_client, admin_headers):
        resp = api_client.post(
            "/api/v2/bo/enum_type/validate",
            json={"data": []},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_validate_create_returns_field_errors(self, api_client, admin_headers):
        resp = api_client.post(
            "/api/v2/bo/enum_type/validate",
            json={"data": {}, "mode": "create"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        payload = body["data"]
        assert isinstance(payload["valid"], bool)
        assert isinstance(payload["errors"], list)

    def test_validate_update_mode(self, api_client, admin_headers):
        resp = api_client.post(
            "/api/v2/bo/enum_type/validate",
            json={"data": {"name": "x"}, "object_id": 1, "mode": "update"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        payload = resp.get_json()["data"]
        assert isinstance(payload["valid"], bool)
        assert isinstance(payload["errors"], list)


class TestSelectionLimit:
    def test_selection_limit_defaults(self, api_client, admin_headers):
        resp = api_client.get("/api/v2/meta/selection-limit", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["max_count"] == 5000
        assert data["warning_threshold"] == 0.8
        assert data["hard_limit"] == 100000


class TestDimensionScopeCoveragePreview:
    def test_preview_returns_contract(self, api_client, admin_headers):
        resp = api_client.get(
            "/api/v1/permission-sets/1/dimension-scopes/scope-preview",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["permission_set_id"] == 1
        assert isinstance(data["objects"], list)
        assert isinstance(data["total"], int)
        assert data["scope_count"] >= 0