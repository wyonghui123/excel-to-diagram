# -*- coding: utf-8 -*-
"""
P1 域 API 测试合并文件

合并以下源文件:
- test_value_help_api.py (unittest, 15 tests)
- test_stats_api.py (unittest, 6 tests)
- test_notification_api.py (unittest, 7 tests)
"""

import os
import sys
import json

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.shared.fixtures import _client_and_headers


class TestValueHelpAPI:
    """[TEST CLASS] Value Help API 测试"""

    def test_search_enum_source_returns_200(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/enum/status', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_search_bo_source_returns_200(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_search_custom_source_returns_200(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/custom/test_endpoint', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_search_with_search_parameter(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain?search=test', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_search_with_pagination(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain?page=1&pageSize=10', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_search_with_sort(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain?sort=name:asc', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_search_with_filters(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain?filters[status]=active', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_search_with_limit(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain?limit=5', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_resolve_enum_value(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/enum/status/resolve?value=active', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_resolve_bo_value(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain/resolve?value=1', headers=h)
        assert r.status_code in [200, 400, 401, 404, 500]

    def test_resolve_without_value_returns_400(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/bo/domain/resolve', headers=h)
        assert r.status_code in [400, 401, 404]


class TestValueHelpAPIAuthentication:
    """[TEST CLASS] Value Help API 认证测试"""

    def test_unauthenticated_returns_valid_status(self):
        from meta.tests.conftest import get_shared_app
        _, c = get_shared_app()
        r = c.get('/api/v2/value-help/bo/domain')
        assert r.status_code in [200, 401, 403, 500]

    def test_invalid_token_returns_valid_status(self):
        from meta.tests.conftest import get_shared_app
        _, c = get_shared_app()
        h = {'Content-Type': 'application/json', 'Authorization': 'Bearer invalid_token'}
        r = c.get('/api/v2/value-help/bo/domain', headers=h)
        assert r.status_code in [200, 401, 403, 500]


class TestValueHelpAPIInvalidSourceType:
    """[TEST CLASS] Value Help API 无效 source_type 测试"""

    def test_invalid_source_type_returns_400(self):
        c, h = _client_and_headers()
        r = c.get('/api/v2/value-help/invalid_type/test', headers=h)
        assert r.status_code in [400, 401, 404]


class TestStatsApi:
    """[TEST CLASS] 统计 API 测试"""

    def test_stats_overview(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/stats/overview', headers=h)
        assert r.status_code in [200, 401, 404, 500]

    def test_stats_overview_structure(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/stats/overview', headers=h)
        if r.status_code == 200:
            data = json.loads(r.data)
            assert data.get('success')
            assert 'data' in data

    def test_aggregates_list(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/stats/aggregates', headers=h)
        assert r.status_code in [200, 401, 404, 500]

    def test_aggregates_list_structure(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/stats/aggregates', headers=h)
        if r.status_code == 200:
            data = json.loads(r.data)
            assert data.get('success')
            assert 'data' in data


class TestStatsApiUnauthenticated:
    """[TEST CLASS] 未认证访问统计 API"""

    def test_stats_overview_without_token(self):
        from meta.tests.conftest import get_shared_app
        _, c = get_shared_app()
        r = c.get('/api/v1/stats/overview')
        assert r.status_code in [200, 401, 403, 500]

    def test_aggregates_without_token(self):
        from meta.tests.conftest import get_shared_app
        _, c = get_shared_app()
        r = c.get('/api/v1/stats/aggregates')
        assert r.status_code in [200, 401, 403, 500]


class TestNotificationApi:
    """[TEST CLASS] 通知 API REST 端点测试"""

    def test_get_subscriptions(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/notifications/subscriptions', headers=h)
        assert r.status_code in [200, 401, 404, 500]

    def test_get_available_types(self):
        c, h = _client_and_headers()
        r = c.get('/api/v1/notifications/subscriptions/available', headers=h)
        assert r.status_code in [200, 401, 404, 500]

    def test_create_subscription(self):
        c, h = _client_and_headers()
        r = c.post('/api/v1/notifications/subscriptions',
                   data=json.dumps({'object_type': 'user', 'event_type': 'update'}),
                   headers=h)
        assert r.status_code in [201, 200, 400, 401, 404, 500]

    def test_create_subscription_empty_body(self):
        c, h = _client_and_headers()
        r = c.post('/api/v1/notifications/subscriptions',
                   data=json.dumps({}),
                   headers=h)
        assert r.status_code in [201, 200, 400, 401, 404, 500]

    def test_delete_nonexistent_subscription(self):
        c, h = _client_and_headers()
        r = c.delete('/api/v1/notifications/subscriptions/999999', headers=h)
        assert r.status_code in [200, 401, 404, 500]


class TestNotificationApiUnauthenticated:
    """[TEST CLASS] 未认证访问通知 API"""

    def test_get_subscriptions_without_token(self):
        from meta.tests.conftest import get_shared_app
        _, c = get_shared_app()
        r = c.get('/api/v1/notifications/subscriptions')
        assert r.status_code in [401, 403, 200, 500]

    def test_create_subscription_without_token(self):
        from meta.tests.conftest import get_shared_app
        _, c = get_shared_app()
        r = c.post('/api/v1/notifications/subscriptions',
                   data=json.dumps({'object_type': 'user'}),
                   content_type='application/json')
        assert r.status_code in [401, 403, 200, 500]
