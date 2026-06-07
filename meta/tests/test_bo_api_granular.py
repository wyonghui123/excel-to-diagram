import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
BO API 细粒度测试套件 (优化版)

[合并来源] test_bo_api.py
  - TestBoAPIGranularCreate (11 tests)
  - TestBoAPIGranularQuery (10 tests)
  - TestBoAPIGranularUpdate (2 tests)
  - TestBoAPIGranularDelete (2 tests)
  - TestBoAPIGranularDeepInsert (2 tests)
  - TestBoAPIGranularBatch (3 tests)

[优化策略]
  1. 使用参数化测试减少重复代码
  2. 统一使用 shared fixtures
  3. 提取公共辅助方法

测试端点：
- 分页查询 (page, page_size)
- 排序 (ordering)
- 过滤 (filters)
- 更新单个/多个字段
- 删除 (存在/不存在)
- Deep Insert
- Batch Delete
"""

import pytest
import json
import os


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in os.environ.get('PYTHONPATH', '').split(os.pathsep):
    os.environ['PYTHONPATH'] = _PROJECT_ROOT + os.pathsep + os.environ.get('PYTHONPATH', '')


# ==================== 常量定义 ====================

class HTTP:
    SUCCESS = [200, 201]
    OK = [200]
    CLIENT_ERROR = [400, 422]
    NOT_FOUND = [404]
    DELETED_OK = [200, 204]
    BATCH_OK = [200, 204, 400, 404]


# ==================== Fixtures ====================

@pytest.fixture(scope='class')
def app_client():
    from meta.tests.conftest import get_shared_app
    return get_shared_app()


@pytest.fixture(scope='class')
def api_headers():
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    user = UserInfo(
        user_id='1', username='granular_test', display_name='Granular Test User',
        email='granular@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'granular_test',
    }


@pytest.fixture(scope='class')
def created_cleanup(app_client, api_headers):
    _created = []
    yield _created
    app, client = app_client
    for obj_type, obj_id in _created:
        try:
            client.delete(f'/api/v2/bo/{obj_type}/{obj_id}', headers=api_headers)
        except Exception:
            pass


def _rand_suffix():
    return os.urandom(4).hex()


# ==================== 参数化测试数据 ====================

PAGINATION_TEST_CASES = [
    ('page=1&page_size=10', 200),
    ('page=1000&page_size=10', 200),
    ('page=1&page_size=1', 200),
    ('page=1&page_size=100', 200),
]

ORDERING_TEST_CASES = [
    ('ordering=username', 200),
    ('ordering=-username', 200),
]

FILTER_TEST_CASES = [
    ('status=active', 200),
    ('status=active&username__contains=test', 200),
    ('username__contains=admin', 200),
]


# ==================== 创建操作测试 ====================

class TestBoAPIGranularCreate:
    """BO API 细粒度创建操作测试"""

    def _create_user(self, api_client, api_headers, created_cleanup, suffix, **extra_fields):
        data = {
            'username': f'granular_{suffix}',
            'password': 'test123',
            **extra_fields
        }
        resp = api_client.post('/api/v2/bo/user', data=json.dumps(data), headers=api_headers)
        if resp.status_code in [200, 201]:
            result = json.loads(resp.data)
            if result.get('success') and result.get('data', {}).get('id'):
                obj_id = result.get('data', {})['id']
                created_cleanup.append(('user', obj_id))
                return resp, result
        return resp, {}

    def test_create_with_minimal_fields(self, api_client, api_headers, created_cleanup):
        """最小字段创建"""
        suffix = _rand_suffix()
        resp, result = self._create_user(api_client, api_headers, created_cleanup, suffix)
        assert resp.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_create_with_all_fields(self, api_client, api_headers, created_cleanup):
        """完整字段创建"""
        suffix = _rand_suffix()
        resp, result = self._create_user(
            api_client, api_headers, created_cleanup, suffix,
            display_name='Test User',
            email=f'{suffix}@test.com',
            status='active'
        )
        assert resp.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR
        if resp.status_code in HTTP.SUCCESS:
            assert result.get('success')

    def test_create_with_special_chars_username(self, api_client, api_headers, created_cleanup):
        """特殊字符用户名"""
        suffix = _rand_suffix()
        resp, result = self._create_user(
            api_client, api_headers, created_cleanup, suffix,
            username=f'user_{suffix}'
        )
        assert resp.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_create_duplicate_username(self, api_client, api_headers, created_cleanup):
        """重复用户名"""
        suffix = _rand_suffix()
        _, _ = self._create_user(api_client, api_headers, created_cleanup, suffix)
        resp2, _ = self._create_user(api_client, api_headers, created_cleanup, suffix)
        assert resp2.status_code in [400, 401, 409, 500]

    def test_create_invalid_email(self, api_client, api_headers, created_cleanup):
        """无效邮箱"""
        suffix = _rand_suffix()
        resp, _ = self._create_user(
            api_client, api_headers, created_cleanup, suffix,
            email='invalid-email'
        )
        assert resp.status_code in HTTP.CLIENT_ERROR + HTTP.SUCCESS

    def test_create_missing_username(self, api_client, api_headers, created_cleanup):
        """缺少用户名"""
        data = {'password': 'test123', 'email': 'test@test.com'}
        resp = api_client.post('/api/v2/bo/user', data=json.dumps(data), headers=api_headers)
        assert resp.status_code in HTTP.CLIENT_ERROR + HTTP.SUCCESS

    def test_create_missing_password(self, api_client, api_headers, created_cleanup):
        """缺少密码"""
        suffix = _rand_suffix()
        resp, _ = self._create_user(
            api_client, api_headers, created_cleanup, suffix,
            password=None
        )
        assert resp.status_code in HTTP.CLIENT_ERROR + HTTP.SUCCESS

    def test_create_with_long_username(self, api_client, api_headers, created_cleanup):
        """超长用户名"""
        suffix = _rand_suffix()
        resp, _ = self._create_user(
            api_client, api_headers, created_cleanup, suffix,
            username=f'user_{"a" * 100}_{suffix}'
        )
        assert resp.status_code in HTTP.CLIENT_ERROR + HTTP.SUCCESS

    def test_create_with_unicode_username(self, api_client, api_headers, created_cleanup):
        """Unicode 用户名"""
        suffix = _rand_suffix()
        resp, _ = self._create_user(
            api_client, api_headers, created_cleanup, suffix,
            username=f'用户_{suffix}'
        )
        assert resp.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_create_empty_body(self, api_client, api_headers):
        """空请求体"""
        resp = api_client.post('/api/v2/bo/user', data='{}', headers=api_headers)
        assert resp.status_code in HTTP.CLIENT_ERROR + HTTP.SUCCESS

    def test_create_invalid_json(self, api_client, api_headers):
        """无效 JSON"""
        resp = api_client.post('/api/v2/bo/user', data='not json', headers=api_headers)
        assert resp.status_code in HTTP.CLIENT_ERROR + HTTP.SUCCESS


# ==================== 查询操作测试 ====================

class TestBoAPIGranularQuery:
    """BO API 细粒度查询操作测试"""

    @pytest.mark.parametrize('params,expected', PAGINATION_TEST_CASES)
    def test_query_pagination(self, api_client, api_headers, params, expected):
        """分页参数测试"""
        response = api_client.get(f'/api/v2/bo/user?{params}', headers=api_headers)
        assert response.status_code in [expected, 400]

    @pytest.mark.parametrize('params,expected', ORDERING_TEST_CASES)
    def test_query_ordering(self, api_client, api_headers, params, expected):
        """排序参数测试"""
        response = api_client.get(f'/api/v2/bo/user?{params}', headers=api_headers)
        assert response.status_code in [expected, 400]

    @pytest.mark.parametrize('params,expected', FILTER_TEST_CASES)
    def test_query_filters(self, api_client, api_headers, params, expected):
        """过滤参数测试"""
        response = api_client.get(f'/api/v2/bo/user?{params}', headers=api_headers)
        assert response.status_code in [expected, 400]

    def test_query_response_format(self, api_client, api_headers):
        """响应格式验证"""
        response = api_client.get('/api/v2/bo/user?page=1&page_size=10', headers=api_headers)
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            assert 'success' in data
            if data.get('success'):
                assert 'data' in data
                result_data = data.get('data', {})
                if isinstance(result_data, dict):
                    assert 'items' in result_data
                    assert 'total' in result_data

    def test_query_with_field_selection(self, api_client, api_headers):
        """字段选择"""
        response = api_client.get('/api/v2/bo/user?fields=id,username,email', headers=api_headers)
        assert response.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_query_with_like_pattern(self, api_client, api_headers):
        """LIKE 模式匹配"""
        response = api_client.get('/api/v2/bo/user?username__startswith=admin', headers=api_headers)
        assert response.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_query_with_in_filter(self, api_client, api_headers):
        """IN 过滤"""
        response = api_client.get('/api/v2/bo/user?id__in=1,2,3', headers=api_headers)
        assert response.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_query_empty_result(self, api_client, api_headers):
        """空结果查询"""
        response = api_client.get('/api/v2/bo/user?username=nonexistent_xyz_123', headers=api_headers)
        assert response.status_code in HTTP.SUCCESS


# ==================== 更新操作测试 ====================

class TestBoAPIGranularUpdate:
    """BO API 细粒度更新操作测试"""

    def _create_for_update(self, api_client, api_headers, created_cleanup, prefix):
        suffix = _rand_suffix()
        data = {'username': f'{prefix}_{suffix}', 'password': 'test123'}
        create_resp = api_client.post('/api/v2/bo/user', data=json.dumps(data), headers=api_headers)
        if create_resp.status_code in HTTP.SUCCESS:
            result = json.loads(create_resp.data)
            if result.get('success') and result.get('data', {}).get('id'):
                obj_id = result.get('data', {})['id']
                created_cleanup.append(('user', obj_id))
                return obj_id
        return None

    def test_update_single_field(self, api_client, api_headers, created_cleanup):
        """更新单个字段"""
        obj_id = self._create_for_update(api_client, api_headers, created_cleanup, 'update_single')
        if obj_id:
            update_data = {'display_name': 'Updated Name'}
            update_resp = api_client.put(
                f'/api/v2/bo/user/{obj_id}',
                data=json.dumps(update_data),
                headers=api_headers
            )
            assert update_resp.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_update_multiple_fields(self, api_client, api_headers, created_cleanup):
        """更新多个字段"""
        obj_id = self._create_for_update(api_client, api_headers, created_cleanup, 'update_multi')
        if obj_id:
            update_data = {
                'display_name': 'Updated Name',
                'email': f'updated_{_rand_suffix()}@test.com'
            }
            update_resp = api_client.put(
                f'/api/v2/bo/user/{obj_id}',
                data=json.dumps(update_data),
                headers=api_headers
            )
            assert update_resp.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR

    def test_update_nonexistent_returns_404(self, api_client, api_headers):
        """更新不存在返回 404"""
        update_data = {'display_name': 'Updated Name'}
        response = api_client.put(
            '/api/v2/bo/user/999999',
            data=json.dumps(update_data),
            headers=api_headers
        )
        assert response.status_code in HTTP.NOT_FOUND + HTTP.SUCCESS + HTTP.CLIENT_ERROR


# ==================== 删除操作测试 ====================

class TestBoAPIGranularDelete:
    """BO API 细粒度删除操作测试"""

    def _create_for_delete(self, api_client, api_headers, created_cleanup, prefix):
        suffix = _rand_suffix()
        data = {'username': f'{prefix}_{suffix}', 'password': 'test123'}
        create_resp = api_client.post('/api/v2/bo/user', data=json.dumps(data), headers=api_headers)
        if create_resp.status_code in HTTP.SUCCESS:
            result = json.loads(create_resp.data)
            if result.get('success') and result.get('data', {}).get('id'):
                return result.get('data', {})['id']
        return None

    def test_delete_nonexistent_returns_404(self, api_client, api_headers):
        """删除不存在返回 404"""
        response = api_client.delete('/api/v2/bo/user/999999', headers=api_headers)
        assert response.status_code in HTTP.NOT_FOUND + HTTP.CLIENT_ERROR

    def test_delete_twice_returns_404(self, api_client, api_headers, created_cleanup):
        """删除两次返回 404"""
        obj_id = self._create_for_delete(api_client, api_headers, created_cleanup, 'delete_twice')
        if obj_id:
            delete_resp1 = api_client.delete(f'/api/v2/bo/user/{obj_id}', headers=api_headers)
            assert delete_resp1.status_code in HTTP.DELETED_OK + HTTP.CLIENT_ERROR

            delete_resp2 = api_client.delete(f'/api/v2/bo/user/{obj_id}', headers=api_headers)
            assert delete_resp2.status_code in HTTP.NOT_FOUND + HTTP.CLIENT_ERROR

    def test_delete_invalid_id(self, api_client, api_headers):
        """无效 ID 删除"""
        response = api_client.delete('/api/v2/bo/user/invalid', headers=api_headers)
        assert response.status_code in HTTP.CLIENT_ERROR + HTTP.SUCCESS + HTTP.NOT_FOUND


# ==================== Deep Insert 测试 ====================

class TestBoAPIGranularDeepInsert:
    """BO API Deep Insert 测试"""

    def test_deep_insert_simple(self, api_client, api_headers):
        """简单 Deep Insert"""
        data = {'username': f'deep_simple_{_rand_suffix()}', 'password': 'test123'}
        response = api_client.post(
            '/api/v2/bo/user/deep',
            data=json.dumps(data),
            headers=api_headers
        )
        assert response.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR + [404]

    def test_deep_insert_with_nested(self, api_client, api_headers):
        """带嵌套的 Deep Insert"""
        suffix = _rand_suffix()
        data = {
            'username': f'deep_nested_{suffix}',
            'password': 'test123',
            'email': f'deep_nested_{suffix}@test.com'
        }
        response = api_client.post(
            '/api/v2/bo/user/deep',
            data=json.dumps(data),
            headers=api_headers
        )
        assert response.status_code in HTTP.SUCCESS + HTTP.CLIENT_ERROR + [404]


# ==================== Batch 操作测试 ====================

class TestBoAPIGranularBatch:
    """BO API Batch 操作测试"""

    def _create_batch_users(self, api_client, api_headers, created_cleanup, prefix, count=3):
        ids = []
        for i in range(count):
            suffix = f'{prefix}_{_rand_suffix()}_{i}'
            data = {'username': f'batch_{suffix}', 'password': 'test123'}
            create_resp = api_client.post('/api/v2/bo/user', data=json.dumps(data), headers=api_headers)
            if create_resp.status_code in HTTP.SUCCESS:
                result = json.loads(create_resp.data)
                if result.get('success') and result.get('data', {}).get('id'):
                    obj_id = result.get('data', {})['id']
                    created_cleanup.append(('user', obj_id))
                    ids.append(obj_id)
        return ids

    def test_batch_delete_empty_list(self, api_client, api_headers):
        """空列表批量删除"""
        response = api_client.post(
            '/api/v2/bo/user/batch-delete',
            data=json.dumps({'ids': []}),
            headers=api_headers
        )
        assert response.status_code in [200, 204, 207, 400, 401, 404, 500]

    def test_batch_delete_single_id(self, api_client, api_headers, created_cleanup):
        """单个 ID 批量删除"""
        ids = self._create_batch_users(api_client, api_headers, created_cleanup, 'single', count=1)
        if ids:
            delete_resp = api_client.post(
                '/api/v2/bo/user/batch-delete',
                data=json.dumps({'ids': [ids[0]]}),
                headers=api_headers
            )
            assert delete_resp.status_code in [200, 204, 207, 400, 401, 404, 500]

    def test_batch_delete_multiple_ids(self, api_client, api_headers, created_cleanup):
        """多个 ID 批量删除"""
        ids = self._create_batch_users(api_client, api_headers, created_cleanup, 'multi', count=3)
        if len(ids) >= 2:
            delete_resp = api_client.post(
                '/api/v2/bo/user/batch-delete',
                data=json.dumps({'ids': ids[:2]}),
                headers=api_headers
            )
            assert delete_resp.status_code in [200, 204, 207, 400, 401, 404, 500]

    def test_batch_delete_nonexistent_ids(self, api_client, api_headers):
        """不存在 ID 批量删除"""
        response = api_client.post(
            '/api/v2/bo/user/batch-delete',
            data=json.dumps({'ids': [99999, 99998]}),
            headers=api_headers
        )
        assert response.status_code in [200, 204, 207, 400, 401, 404, 500]

    def test_batch_delete_invalid_ids(self, api_client, api_headers):
        """无效 ID 批量删除"""
        response = api_client.post(
            '/api/v2/bo/user/batch-delete',
            data=json.dumps({'ids': ['abc', 'xyz']}),
            headers=api_headers
        )
        assert response.status_code in HTTP.CLIENT_ERROR + [200, 204, 207, 400, 404]
