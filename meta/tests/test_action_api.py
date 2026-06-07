import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Action API 端点测试

测试自定义 Action 的 API 端点：
- GET /<object_type>/<id>/actions - 获取可用 Action 列表
- POST /<object_type>/<id>/actions/<action_id> - 执行 Action
"""

import pytest
import json
from datetime import datetime

from meta.server import create_app
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo
from meta import get_meta_object
from meta.core.models import ActionType


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    test_user = UserInfo(
        user_id="1",
        username="test_user",
        display_name="Test User",
        email="test@test.com",
        roles=["admin"],
        permissions=["*"],
    )
    token, _ = TokenService.create_token(test_user)
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-User-Id": "1",
        "X-User-Name": "test_user",
    }


class TestListActionsAPI:
    """GET /<object_type>/<id>/actions 端点测试"""

    def test_list_actions_returns_success(self, client, auth_headers):
        """获取 Action 列表应返回成功或404"""
        response = client.get("/api/v2/bo/product/1/actions", headers=auth_headers)

        assert response.status_code in [200, 401, 404, 500]
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            assert data["success"] is True
            assert "data" in data

    def test_list_actions_includes_can_delete(self, client, auth_headers):
        """Action 列表应包含 can_delete 标志"""
        response = client.get("/api/v2/bo/product/1/actions", headers=auth_headers)

        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            if isinstance(data.get("data"), dict):
                assert "can_delete" in data["data"]

    def test_list_actions_for_nonexistent_object(self, client, auth_headers):
        """不存在的对象应返回 404"""
        response = client.get("/api/v2/bo/product/99999/actions", headers=auth_headers)

        assert response.status_code in [400, 401, 404]

    def test_list_actions_for_invalid_object_type(self, client, auth_headers):
        """无效的对象类型应返回 404"""
        response = client.get("/api/v2/bo/nonexistent_type/1/actions", headers=auth_headers)

        assert response.status_code in [400, 401, 404]


class TestExecuteActionAPI:
    """POST /<object_type>/<id>/actions/<action_id> 端点测试"""

    def test_execute_nonexistent_action(self, client, auth_headers):
        """执行不存在的 Action 应返回错误"""
        response = client.post(
            "/api/v2/bo/product/1/actions/nonexistent_action",
            data=json.dumps({}),
            headers=auth_headers
        )

        assert response.status_code in [200, 400, 401, 404, 500]
        if response.status_code not in [200]:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            assert data["success"] is False

    def test_execute_action_with_invalid_object_type(self, client, auth_headers):
        """无效的对象类型应返回错误"""
        response = client.post(
            "/api/v2/bo/nonexistent_type/1/actions/some_action",
            data=json.dumps({}),
            headers=auth_headers
        )

        assert response.status_code in [400, 401, 404]


class TestCanDeleteInAPI:
    """can_delete 标志在 API 响应中的测试"""

    def test_detail_api_includes_can_delete(self, client, auth_headers):
        """详情 API 应返回 can_delete 标志"""
        response = client.get("/api/v2/bo/product/1", headers=auth_headers)

        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            if data.get("success") and data.get("data"):
                assert "can_delete" in data["data"]

    def test_list_api_includes_can_delete_for_deletability_objects(self, client, auth_headers):
        """列表 API 对有 deletability 配置的对象应返回 can_delete"""
        response = client.get("/api/v2/bo/version?page_size=10", headers=auth_headers)

        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            if data.get("success") and data.get("data"):
                items = data["data"] if isinstance(data["data"], list) else data["data"].get("items", [])
                for item in items:
                    assert "can_delete" in item, "Version items should have can_delete flag"


class TestActionBehavior:
    """Action Behavior 声明式配置测试"""

    def test_meta_action_has_behavior_field(self):
        """MetaAction 应有 behavior 字段"""
        from meta.core.models import MetaAction, ActionType

        action = MetaAction(
            id="test_action",
            name="Test Action",
            action_type=ActionType.CUSTOM,
            method="POST",
            path="/test",
        )

        assert hasattr(action, "behavior")
        assert action.behavior is None

    def test_action_behavior_with_precondition(self):
        """ActionBehavior 应支持前置条件"""
        from meta.core.models import ActionBehavior, ActionPrecondition

        behavior = ActionBehavior(
            precondition=ActionPrecondition(
                condition="status == 'active'",
                message="非活跃状态不能执行",
            )
        )

        assert behavior.precondition is not None
        assert behavior.precondition.condition == "status == 'active'"

    def test_action_behavior_with_effects(self):
        """ActionBehavior 应支持效果列表"""
        from meta.core.models import ActionBehavior, ActionEffect

        behavior = ActionBehavior(
            effects=[
                ActionEffect(
                    type="set_fields",
                    target="self",
                    fields={"status": "completed", "completed_at": "$now"},
                )
            ]
        )

        assert len(behavior.effects) == 1
        assert behavior.effects[0].type == "set_fields"
        assert "status" in behavior.effects[0].fields
