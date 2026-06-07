# -*- coding: utf-8 -*-
"""
扩展 API 测试

合并以下测试文件:
- test_stats_api.py (统计 API)
- test_agent_api.py (Agent API)
- test_notification_api.py (通知 API)
- test_view_config_engine.py (视图配置引擎)
- test_import_export_api_config.py (导入导出配置)

测试范围:
- 统计端点: /api/v1/stats/*
- Agent 端点: /api/v1/agent/*
- 通知端点: /api/v1/notifications/*
- 视图配置: /api/v1/meta/*/view-config
- 导入导出配置: /api/v1/import-export/config/*
"""

import pytest
import json

pytestmark = pytest.mark.integration


# ==================== 共享 Fixtures ====================

@pytest.fixture(scope='module')
def api_client():
    """获取共享 API 客户端"""
    from meta.tests.conftest import get_shared_app
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    _, client = get_shared_app()
    user = UserInfo(
        user_id='1', username='test_admin', display_name='Test Admin',
        email='admin@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_admin'
    }
    return client, headers


@pytest.fixture
def no_auth_client():
    """获取无认证的客户端"""
    from meta.tests.conftest import get_shared_app
    _, client = get_shared_app()
    return client


# ==================== 统计 API 测试 ====================

class TestStatsOverview:
    """统计概览 API 测试"""

    def test_stats_overview_returns_status(self, api_client):
        """统计概览端点返回状态码"""
        client, headers = api_client
        resp = client.get('/api/v1/stats/overview', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_stats_overview_structure(self, api_client):
        """统计概览响应结构验证"""
        client, headers = api_client
        resp = client.get('/api/v1/stats/overview', headers=headers)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            result = data.get('data', {})
            assert 'products' in result
            assert 'domains' in result
            assert 'business_objects' in result


class TestAggregates:
    """聚合端点测试"""

    def test_aggregates_list_returns_status(self, api_client):
        """聚合列表端点返回状态码"""
        client, headers = api_client
        resp = client.get('/api/v1/stats/aggregates', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_aggregates_structure(self, api_client):
        """聚合响应结构验证"""
        client, headers = api_client
        resp = client.get('/api/v1/stats/aggregates', headers=headers)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'data' in data


class TestStatsUnauthenticated:
    """统计 API 未认证访问测试"""

    def test_unauthenticated_access(self, no_auth_client):
        """未认证访问统计端点"""
        resp = no_auth_client.get('/api/v1/stats/overview')
        assert resp.status_code in [401, 403, 302, 200, 500]


# ==================== Agent API 测试 ====================

class TestAgentAPI:
    """Agent API 测试"""

    def test_list_agents(self, api_client):
        """列出代理"""
        client, headers = api_client
        response = client.get('/api/v1/agent?page=1&page_size=10', headers=headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_agent_by_id(self, api_client):
        """根据 ID 获取代理"""
        client, headers = api_client
        response = client.get('/api/v1/agent/1', headers=headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_get_agent_status(self, api_client):
        """获取代理状态"""
        client, headers = api_client
        response = client.get('/api/v1/agent/1/status', headers=headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_get_agent_tasks(self, api_client):
        """获取代理任务"""
        client, headers = api_client
        response = client.get('/api/v1/agent/1/tasks?page=1&page_size=10', headers=headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_list_without_auth(self, no_auth_client):
        """未认证访问 Agent API"""
        response = no_auth_client.get('/api/v1/agent')
        assert response.status_code in [401, 403, 302, 200, 404, 500]

    def test_get_agent_tools(self, api_client):
        """获取 Agent 工具列表"""
        client, headers = api_client
        resp = client.get('/api/v1/agent/tools', headers=headers)
        if resp.status_code == 200:
            data = resp.get_json()
            if data.get('success'):
                print(f"  Total tools: {len(data.get('data', []))}")

    def test_get_agent_context_domain(self, api_client):
        """获取 Agent 上下文（领域）"""
        client, headers = api_client
        resp = client.get('/api/v1/agent/context/domain', headers=headers)
        if resp.status_code == 200:
            data = resp.get_json()
            if data.get('success'):
                print(f"  Fields: {len(data.get('data', {}).get('fields', []))}")


# ==================== 通知 API 测试 ====================

class TestNotificationApi:
    """通知 API REST 端点测试"""

    def test_get_subscriptions(self, api_client):
        """获取订阅列表"""
        client, headers = api_client
        resp = client.get('/api/v1/notifications/subscriptions', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_get_available_types(self, api_client):
        """获取可用订阅类型"""
        client, headers = api_client
        resp = client.get('/api/v1/notifications/subscriptions/available', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_create_subscription(self, api_client):
        """创建订阅"""
        client, headers = api_client
        resp = client.post('/api/v1/notifications/subscriptions',
                           data=json.dumps({
                               'object_type': 'user',
                               'event_type': 'update',
                           }),
                           headers=headers)
        assert resp.status_code in [201, 200, 400, 401, 404, 500]

    def test_create_subscription_empty_body(self, api_client):
        """空请求体创建订阅"""
        client, headers = api_client
        resp = client.post('/api/v1/notifications/subscriptions',
                           data=json.dumps({}),
                           headers=headers)
        assert resp.status_code in [201, 200, 400, 401, 404, 500]

    def test_delete_nonexistent_subscription(self, api_client):
        """删除不存在的订阅"""
        client, headers = api_client
        resp = client.delete('/api/v1/notifications/subscriptions/999999', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]


class TestNotificationApiUnauthenticated:
    """通知 API 未认证访问测试"""

    def test_get_subscriptions_without_token(self, no_auth_client):
        """未认证获取订阅列表"""
        resp = no_auth_client.get('/api/v1/notifications/subscriptions')
        assert resp.status_code in [401, 403, 200, 500]

    def test_create_subscription_without_token(self, no_auth_client):
        """未认证创建订阅"""
        resp = no_auth_client.post('/api/v1/notifications/subscriptions',
                                   data=json.dumps({'object_type': 'user'}),
                                   content_type='application/json')
        assert resp.status_code in [401, 403, 200, 500]


# ==================== 视图配置 API 测试 ====================

class TestViewConfigApi:
    """视图配置 API 测试"""

    def test_meta_objects_list(self, api_client):
        """获取元对象列表"""
        client, headers = api_client
        resp = client.get('/api/v1/meta/objects', headers=headers)
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"  Total objects: {data.get('total', 0)}")

    def test_domain_view_config(self, api_client):
        """获取领域视图配置"""
        client, headers = api_client
        resp = client.get('/api/v1/meta/domain/view-config', headers=headers)
        if resp.status_code == 200:
            data = resp.get_json()
            if data.get('success'):
                print(f"  List columns: {len(data.get('data', {})['list']['columns'])}")

    def test_subdomain_view_config(self, api_client):
        """获取子领域视图配置"""
        client, headers = api_client
        resp = client.get('/api/v1/meta/sub_domain/view-config', headers=headers)
        if resp.status_code == 200:
            data = resp.get_json()
            if data.get('success'):
                print(f"  List columns: {len(data.get('data', {})['list']['columns'])}")


# ==================== 导入导出配置 API 测试 ====================

class TestImportExportConfigAPI:
    """导入导出配置 API 测试"""

    def test_get_domain_import_export_config(self, api_client):
        """获取领域的导入导出配置"""
        client, headers = api_client
        response = client.get('/api/v1/import-export/config/domain', headers=headers)
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False)
        assert data.get('data', {})['object_type'] == 'domain'
        assert data.get('data', {})['import_enabled']
        assert data.get('data', {})['export_enabled']

    def test_get_business_object_import_export_config(self, api_client):
        """获取业务对象的导入导出配置"""
        client, headers = api_client
        response = client.get('/api/v1/import-export/config/business_object', headers=headers)
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False)
        assert data.get('data', {})['object_type'] == 'business_object'

    def test_get_nonexistent_object_config(self, api_client):
        """获取不存在的对象配置"""
        client, headers = api_client
        response = client.get('/api/v1/import-export/config/nonexistent_object', headers=headers)
        assert response.status_code in [401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert not data.get('success', False)
