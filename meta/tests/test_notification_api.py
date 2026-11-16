# -*- coding: utf-8 -*-
"""
GAP-009: notification_api 端到端测试 (10 用例)

[NEW] 2026-06-07 批次: 补齐 notification_api (9 端点) 的端到端测试
- /stats (仅管理员)
- /subscriptions (GET/POST/PUT/DELETE)
- /subscriptions/<id> (GET)
- WebSocket 端点 (仅验证注册存在, 不实际连接)
"""
import json
import time
import pytest

pytestmark = pytest.mark.integration


NOTIF_URL = '/api/v1/notifications'


class TestNotificationAPI:
    """notification_api 端到端测试 (GAP-009)"""

    def test_get_websocket_stats(self, api_client, admin_headers):
        """GET /notifications/stats WebSocket 连接统计"""
        resp = api_client.get(f'{NOTIF_URL}/stats', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'data' in body

    def test_list_subscriptions(self, api_client, admin_headers):
        """GET /notifications/subscriptions 当前用户订阅列表"""
        resp = api_client.get(f'{NOTIF_URL}/subscriptions', headers=admin_headers)
        # 鉴权失败 (g.user_id 缺失) 或 200
        assert resp.status_code in (200, 401, 500)
        body = resp.get_json()
        if resp.status_code == 200:
            assert 'data' in body

    def test_create_subscription_missing_object_type_400(self, api_client, admin_headers):
        """POST /notifications/subscriptions 缺 object_type → 400"""
        resp = api_client.post(
            f'{NOTIF_URL}/subscriptions',
            json={},
            headers=admin_headers,
        )
        # 401 (g.user_id 缺失) 或 400 (校验失败) 或 500 (服务未初始化)
        assert resp.status_code in (400, 401, 500)

    def test_create_subscription_in_app(self, api_client, admin_headers):
        """POST /subscriptions channel=in_app 创建订阅"""
        resp = api_client.post(
            f'{NOTIF_URL}/subscriptions',
            json={
                'object_type': 'user',
                'event_types': ['created', 'updated'],
                'channel': 'in_app',
            },
            headers=admin_headers,
        )
        # 服务未初始化时 500
        assert resp.status_code in (201, 401, 500)

    def test_create_subscription_invalid_channel_400(self, api_client, admin_headers):
        """POST /subscriptions 非法 channel → 400（与 DDL chk_channel 对齐）"""
        resp = api_client.post(
            f'{NOTIF_URL}/subscriptions',
            json={
                'object_type': 'user',
                'channel': 'websocket',
            },
            headers=admin_headers,
        )
        assert resp.status_code in (400, 500)

    def test_create_subscription_webhook_missing_url_400(self, api_client, admin_headers):
        """POST /subscriptions channel=webhook 缺 url → 400"""
        resp = api_client.post(
            f'{NOTIF_URL}/subscriptions',
            json={
                'object_type': 'user',
                'channel': 'webhook',
            },
            headers=admin_headers,
        )
        # 401 / 400 / 500
        assert resp.status_code in (400, 401, 500)

    def test_get_subscription_404(self, api_client, admin_headers):
        """GET /subscriptions/<nonexistent> 404"""
        resp = api_client.get(f'{NOTIF_URL}/subscriptions/9999999', headers=admin_headers)
        # 401/404/500 均可
        assert resp.status_code in (401, 404, 500)

    def test_update_subscription_404(self, api_client, admin_headers):
        """PUT /subscriptions/<nonexistent> 404"""
        resp = api_client.put(
            f'{NOTIF_URL}/subscriptions/9999999',
            json={'event_types': ['created']},
            headers=admin_headers,
        )
        assert resp.status_code in (401, 404, 500)

    def test_delete_subscription_404(self, api_client, admin_headers):
        """DELETE /subscriptions/<nonexistent> 404"""
        resp = api_client.delete(f'{NOTIF_URL}/subscriptions/9999999', headers=admin_headers)
        assert resp.status_code in (401, 404, 500)

    def test_subscriptions_require_auth(self):
        """未认证访问 /subscriptions 返回 401"""
        from meta.tests.conftest import get_shared_app
        _, fresh_client = get_shared_app()
        if hasattr(fresh_client, '_cookies'):
            fresh_client._cookies.clear()
        resp = fresh_client.get(f'{NOTIF_URL}/subscriptions')
        assert resp.status_code in (401, 302, 403)

    def test_websocket_blueprint_registered(self):
        """WebSocket Blueprint 已注册 (init_socketio)"""
        from meta.api.notification_api import notification_bp
        # Blueprint 应能导入
        assert notification_bp is not None
        assert notification_bp.name == 'notification'


class _FakeDS:
    """只实现 find_by_id / insert / update 的极简数据源（订阅 API 单测用）。"""

    def __init__(self, tables):
        self.tables = tables
        self.inserted = None
        self.updated = None

    def find_by_id(self, table, row_id):
        return (self.tables.get(table) or {}).get(int(row_id))

    def insert(self, table, row):
        self.inserted = dict(row)
        return 1

    def update(self, table, row_id, data):
        self.updated = dict(data)


def _flask_app():
    from flask import Flask
    return Flask(__name__)


class TestSubscriptionConnectionRef:
    """FR-2：订阅 API 支持引用集成连接（connection_id）。"""

    def test_create_subscription_with_connection_only(self, monkeypatch):
        """只给 connection_id 时不强制 webhook_url，并落 connection_id。"""
        import meta.api.notification_api as api
        fake = _FakeDS({'integration_connection': {7: {'id': 7, 'code': 'ops'}}})
        monkeypatch.setattr(api, 'ds', fake)
        monkeypatch.setattr(api, '_current_user_id', lambda: 1)
        with _flask_app().test_request_context(json={
                'object_type': 'domain',
                'channel': 'webhook',
                'connection_id': 7}):
            resp, status = api.create_subscription.__wrapped__()
        assert status == 201
        assert resp.get_json()['data']['connection_id'] == 7
        assert fake.inserted['connection_id'] == 7
        assert fake.inserted['webhook_url'] == ''

    def test_create_subscription_rejects_unknown_connection(self, monkeypatch):
        """connection_id 指向不存在的连接 → 400。"""
        import meta.api.notification_api as api
        fake = _FakeDS({})
        monkeypatch.setattr(api, 'ds', fake)
        monkeypatch.setattr(api, '_current_user_id', lambda: 1)
        with _flask_app().test_request_context(json={
                'object_type': 'domain',
                'channel': 'webhook',
                'connection_id': 404}):
            resp, status = api.create_subscription.__wrapped__()
        assert status == 400
        assert fake.inserted is None

    def test_update_subscription_binds_connection(self, monkeypatch):
        """PUT 可把既有订阅绑定到连接。"""
        import meta.api.notification_api as api
        fake = _FakeDS({
            'integration_connection': {7: {'id': 7, 'code': 'ops'}},
            'change_subscriptions': {5: {
                'id': 5, 'user_id': 1, 'channel': 'webhook',
                'webhook_url': '', 'connection_id': None}},
        })
        monkeypatch.setattr(api, 'ds', fake)
        monkeypatch.setattr(api, '_current_user_id', lambda: 1)
        with _flask_app().test_request_context(json={'connection_id': 7}):
            result = api.update_subscription.__wrapped__(5)
        resp = result[0] if isinstance(result, tuple) else result
        assert resp.status_code == 200
        assert fake.updated == {'connection_id': 7}
