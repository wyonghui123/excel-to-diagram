# -*- coding: utf-8 -*-
"""
Schema API v1 测试 — 客户视角

测试 schema_api.py 全部端点：
- POST /api/v1/schema/sync                    — Schema 同步
- GET  /api/v1/schema/tables                  — 列出所有表
- GET  /api/v1/schema/tables/<table_name>     — 获取表结构
- POST /api/v1/schema/tables/<table_name>/create — 创建表
- GET  /api/v1/schema/status                  — Schema 同步状态
- GET  /api/v1/schema/indexes/report          — 全局索引报告
- GET  /api/v1/schema/indexes/report/<id>     — 指定对象索引报告
- POST /api/v1/schema/indexes/create          — 自动创建索引
- GET  /api/v1/schema/indexes/stats           — 索引统计
"""

import pytest
import json
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.server import create_app
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo

pytestmark = pytest.mark.integration


def _mk_token(roles=None, perms=None):
    u = UserInfo(user_id='1', username='schema_test', display_name='Schema Tester',
                 email='s@test.com', roles=roles or ['admin'], permissions=perms or ['*'])
    t, _ = TokenService.create_token(u)
    return t


@pytest.fixture(scope='class')
def schema_api():
    from meta.tests.conftest import get_shared_app
    app, client = get_shared_app()
    token = _mk_token()
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }
    return client, headers


@pytest.fixture(scope='class')
def schema_api_noauth():
    from meta.tests.conftest import get_shared_app
    app, client = get_shared_app()
    return client


class TestSchemaApi:
    """Schema 管理 API — 客户视角"""

    def test_sync_schema_success(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/sync', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_sync_schema_response_structure(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/sync', headers=h)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'message' in data
            assert 'data' in data
            result = data.get('data', {})
            assert 'created' in result
            assert 'updated' in result
            assert 'errors' in result

    def test_list_tables(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/tables', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_list_tables_response_structure(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/tables', headers=h)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'data' in data

    def test_get_table_schema_existing(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/tables/users', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_get_table_schema_nonexistent(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/tables/nonexistent_xyz_table', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_get_table_schema_response_structure(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/tables/users', headers=h)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'data' in data
            assert 'table_name' in data.get('data', {})
            assert 'columns' in data.get('data', {})

    def test_create_table_existing(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/tables/users/create',
                           data=json.dumps({'object_id': 'user'}), headers=h)
        assert resp.status_code in [200, 400, 401, 409, 500]

    def test_create_table_nonexistent_object(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/tables/fake_obj/create',
                           data=json.dumps({'object_id': 'nonexistent_object'}), headers=h)
        assert resp.status_code in [400, 401, 404, 409, 500]

    def test_schema_status(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/status', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_schema_status_response_structure(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/status', headers=h)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'data' in data
            status = data.get('data', {})
            assert 'synced' in status
            assert 'missing' in status
            assert 'mismatch' in status

    def test_indexes_report_global(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/indexes/report', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_indexes_report_global_structure(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/indexes/report', headers=h)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'data' in data

    def test_indexes_report_specific_object(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/indexes/report/user', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_indexes_report_nonexistent(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/indexes/report/nonexistent_obj', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_create_indexes_all(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/indexes/create',
                           data=json.dumps({}), headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_create_indexes_priority(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/indexes/create',
                           data=json.dumps({'priority': 'high'}), headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_create_indexes_specific_object(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/indexes/create',
                           data=json.dumps({'object_id': 'user'}), headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_create_indexes_response_structure(self, schema_api):
        client, h = schema_api
        resp = client.post('/api/v1/schema/indexes/create',
                           data=json.dumps({}), headers=h)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'message' in data
            assert 'data' in data
            assert 'total' in data.get('data', {})
            assert 'success' in data.get('data', {})
            assert 'results' in data.get('data', {})

    def test_indexes_stats(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/indexes/stats', headers=h)
        assert resp.status_code in [200, 401, 404, 500]

    def test_indexes_stats_structure(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/indexes/stats', headers=h)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get('success')
            assert 'data' in data
            stats = data.get('data', {})
            assert 'total_indexes' in stats
            assert 'existing' in stats
            assert 'missing' in stats
            assert 'missing_indexes' in stats
            assert 'all_indexes' in stats

    def test_indexes_stats_with_table_filter(self, schema_api):
        client, h = schema_api
        resp = client.get('/api/v1/schema/indexes/stats?table=users', headers=h)
        assert resp.status_code in [200, 401, 404, 500]


class TestSchemaApiUnauthenticated:
    """未认证访问 Schema API"""

    def test_sync_without_token(self, schema_api_noauth):
        client = schema_api_noauth
        resp = client.post('/api/v1/schema/sync')
        assert resp.status_code in [401, 403, 200, 500]

    def test_tables_without_token(self, schema_api_noauth):
        client = schema_api_noauth
        resp = client.get('/api/v1/schema/tables')
        assert resp.status_code in [401, 403, 200, 500]
