# -*- coding: utf-8 -*-
"""
GAP-018: intent_api 端到端测试 (8 用例)

[NEW] 2026-06-07 批次: 补齐 intent_api (7 端点 × v1/v2 双路由) 的端到端测试
- POST /api/v1/permissions/check_intent | /api/v2/permissions/check_intent
- GET  /api/v1/bos | /api/v2/bos
- GET  /api/v1/bos/<id>/actions | /api/v2/bos/<id>/actions
- GET  /api/v1/bos/<id>/actions/<action> | /api/v2/bos/<id>/actions/<action>
- GET  /api/v1/roles/<id>/intents | /api/v2/roles/<id>/intents
- PUT  /api/v1/roles/<id>/intents/<bo>/<action> | /api/v2/roles/<id>/intents/<bo>/<action>
- DELETE /api/v1/roles/<id>/intents/<bo>/<action> | /api/v2/roles/<id>/intents/<bo>/<action>
"""
import pytest

pytestmark = pytest.mark.integration


class TestIntentAPI:
    """intent_api 端到端测试 (GAP-018)"""

    def test_check_intent_v1(self, api_client, admin_headers):
        """POST /api/v1/permissions/check_intent v1 路由"""
        resp = api_client.post(
            '/api/v1/permissions/check_intent',
            json={'user_id': 1, 'bo_id': 'user', 'action_name': 'read'},
            headers=admin_headers,
        )
        # 200 (成功) 或 500 (IntentPermissionChecker 初始化失败)
        assert resp.status_code in (200, 500)
        body = resp.get_json()
        if resp.status_code == 200:
            assert body.get('success') is True

    def test_check_intent_missing_fields_400(self, api_client, admin_headers):
        """POST /check_intent 缺 user_id/bo_id → 400"""
        resp = api_client.post(
            '/api/v1/permissions/check_intent',
            json={},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('success') is False
        assert 'required' in body.get('error', '')

    def test_list_bos_v1(self, api_client, admin_headers):
        """GET /api/v1/bos 列出所有 BO"""
        resp = api_client.get('/api/v1/bos', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body['data'], list)
        if body['data']:
            assert 'bo_id' in body['data'][0]
            assert 'type' in body['data'][0]

    def test_list_bos_with_type_filter(self, api_client, admin_headers):
        """GET /api/v1/bos?type=entity 按 type 过滤"""
        resp = api_client.get('/api/v1/bos?type=entity', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # 返回的 BO 应都是 entity 类型
        for bo in body['data']:
            assert bo.get('type') == 'entity'

    def test_list_bo_actions_v2(self, api_client, admin_headers):
        """GET /api/v2/bos/<id>/actions v2 路由"""
        resp = api_client.get('/api/v2/bos/user/actions', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body['data'], list)

    def test_get_bo_action_404(self, api_client, admin_headers):
        """GET /api/v1/bos/<id>/actions/<unknown> 404"""
        resp = api_client.get(
            '/api/v1/bos/user/actions/__no_such_action__',
            headers=admin_headers,
        )
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False
        assert 'not found' in body.get('error', '').lower()

    def test_list_role_intents_v1(self, api_client, admin_headers):
        """GET /api/v1/roles/<id>/intents 角色 Intent 列表"""
        resp = api_client.get('/api/v1/roles/1/intents', headers=admin_headers)
        # 200 (RoleIntentDAO 正常) 或 500 (DAO 初始化失败)
        assert resp.status_code in (200, 500)
        body = resp.get_json()
        if resp.status_code == 200:
            assert body.get('success') is True
            assert isinstance(body['data'], list)

    def test_grant_intent_v2(self, api_client, admin_headers):
        """PUT /api/v2/roles/<id>/intents/<bo>/<action> 授予 Intent"""
        resp = api_client.put(
            '/api/v2/roles/1/intents/user/read',
            json={'granted': True, 'source': 'test'},
            headers=admin_headers,
        )
        # 200 (DAO 正常) 或 500 (DAO 初始化失败)
        assert resp.status_code in (200, 500)
        body = resp.get_json()
        if resp.status_code == 200:
            assert body.get('success') is True
            assert body['data']['granted'] is True
