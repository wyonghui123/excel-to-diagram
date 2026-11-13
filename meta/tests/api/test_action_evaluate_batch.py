# -*- coding: utf-8 -*-
"""T13-6 / B1-2 批量动作求值接口测试

覆盖 POST /api/v2/bo/<object_type>/actions/evaluate：
- 未知 / 无法识别的 action 不得 fail-open（不出现 enabled=true）
- 无权限 → enabled=false + reason=no_permission
- 批量多 id → 每个 id 独立桶
- 权限检查抛异常 → fail-closed，不得放行
"""

import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration

ENDPOINT = "/api/v2/bo/enum_type/actions/evaluate"


@pytest.fixture(scope="module")
def api_client():
    from meta.tests.conftest import get_shared_app

    return get_shared_app()[1]


def _make_headers(user_id, roles, permissions):
    from meta.services.auth_provider import UserInfo
    from meta.services.token_service import TokenService

    user = UserInfo(
        user_id=str(user_id),
        username=f"user{user_id}",
        display_name="T13-6",
        email="t13-6@test.com",
        roles=list(roles),
        permissions=list(permissions),
    )
    token, _ = TokenService.create_token(user)
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_headers(api_client):
    return _make_headers(1, ["admin"], ["*"])


@pytest.fixture(scope="module")
def viewer_headers(api_client):
    # 用户不存在于库中 → 权限集为空 → 权限检查一律拒绝
    return _make_headers(987654, ["viewer"], [])


class TestActionEvaluateBatchContract:

    def test_unknown_object_returns_404(self, api_client, admin_headers):
        resp = api_client.post(
            "/api/v2/bo/__not_exists__/actions/evaluate",
            json={"ids": [1], "actions": [{"id": "view"}]},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_ids_must_be_list(self, api_client, admin_headers):
        resp = api_client.post(ENDPOINT, json={"ids": 1, "actions": []}, headers=admin_headers)
        assert resp.status_code == 400

    def test_actions_must_be_list(self, api_client, admin_headers):
        resp = api_client.post(ENDPOINT, json={"ids": [1], "actions": "view"}, headers=admin_headers)
        assert resp.status_code == 400

    def test_unidentified_action_not_fail_open(self, api_client, admin_headers):
        """无法识别的动作（缺 id/key）不得被判为 enabled=true。"""
        resp = api_client.post(
            ENDPOINT,
            json={"ids": [1], "actions": [{"label": "缺少 id"}, {"id": "view"}]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "1" in data
        # 只有可识别的动作产生 verdict，其余保持"未求值"（前端 fail-closed）
        assert set(data["1"].keys()) == {"view"}
        assert data["1"]["view"]["enabled"] is True

    def test_plain_string_action_id_supported(self, api_client, admin_headers):
        """字符串形式的动作 id 也应被识别（不再静默跳过）。"""
        resp = api_client.post(
            ENDPOINT,
            json={"ids": [1], "actions": ["view"]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["1"]["view"]["enabled"] is True

    def test_no_permission_denied(self, api_client, viewer_headers):
        resp = api_client.post(
            ENDPOINT,
            json={
                "ids": [1],
                "actions": [{"id": "edit", "permission": "enum_type:enum_type_update"}],
            },
            headers=viewer_headers,
        )
        assert resp.status_code == 200
        verdict = resp.get_json()["data"]["1"]["edit"]
        assert verdict["enabled"] is False
        assert verdict["reason"] == "no_permission"
        assert verdict["required_permission"] == "enum_type:enum_type_update"

    def test_batch_multiple_ids(self, api_client, admin_headers):
        resp = api_client.post(
            ENDPOINT,
            json={"ids": [1, 2], "actions": [{"id": "view"}]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert set(data.keys()) == {"1", "2"}
        assert data["1"]["view"]["enabled"] is True
        assert data["2"]["view"]["enabled"] is True

    def test_permission_checker_exception_fail_closed(self, api_client, admin_headers, monkeypatch):
        """权限后端抛异常时不得 fail-open 放行。"""
        from meta.services.permission_service import PermissionService

        def _raise(_self, _user_id, _code):
            raise RuntimeError('permission backend down')

        monkeypatch.setattr(PermissionService, 'has_permission', _raise)
        resp = api_client.post(
            ENDPOINT,
            json={"ids": [1], "actions": [{"id": "edit", "permission": "enum_type:enum_type_update"}]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        verdict = resp.get_json()["data"]["1"]["edit"]
        assert verdict["enabled"] is False
        assert verdict["reason"] == "no_permission"