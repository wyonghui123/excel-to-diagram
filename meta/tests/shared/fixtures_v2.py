# -*- coding: utf-8 -*-
"""
[MODULE] 增强版测试 Fixtures
[DESCRIPTION] 提供 cleanup_tracker, cleanup_list, bulk_cleanup 等实用 fixtures

使用方式：
1. 在测试文件中导入：
   from meta.tests.shared.fixtures_v2 import cleanup_tracker, cleanup_list, create_test_object

2. 在测试中使用：
   def test_create(cleanup_list):
       user_id = create_test_object('user', {'username': 'test', ...})
       cleanup_list.append(('user', user_id))
"""

import pytest
import json
import os
import time
from typing import Dict, List, Any, Optional, Tuple


# ==================== 资源清理 Fixtures ====================

@pytest.fixture
def cleanup_tracker(api_client, admin_headers):
    """
    [FIXTURE] 资源清理跟踪器
    [DESCRIPTION] 自动清理测试中创建的 API 资源
    [USAGE]
        def test_create(cleanup_tracker):
            # 创建用户
            resp = api_client.post('/api/v2/bo/user', json=data, headers=admin_headers)
            user_id = json.loads(resp.data)['data']['id']
            cleanup_tracker.append(('user', user_id))
    [CLEANUP] 测试结束后自动删除所有跟踪的资源
    """
    cleanup_list = []
    yield cleanup_list

    for obj_type, obj_id in reversed(cleanup_list):
        try:
            api_client.delete(
                f'/api/v2/bo/{obj_type}/{obj_id}',
                headers=admin_headers
            )
        except Exception:
            pass


@pytest.fixture
def cleanup_list(api_client, admin_headers):
    """
    [FIXTURE] 简化的资源清理列表
    [DESCRIPTION] 与 cleanup_tracker 功能相同，命名更简洁
    [USAGE]
        def test_api(cleanup_list):
            # 创建资源
            cleanup_list.append(('user', 123))
            cleanup_list.append(('role', 456))
    [NOTE] 简写形式
    """
    return cleanup_tracker(api_client, admin_headers)


@pytest.fixture
def bulk_cleanup(api_client, admin_headers):
    """
    [FIXTURE] 批量清理器
    [DESCRIPTION] 支持批量操作和条件清理
    [USAGE]
        def test_bulk(bulk_cleanup):
            # 创建多个资源
            user_ids = [1, 2, 3]
            for uid in user_ids:
                bulk_cleanup.add('user', uid)
    """
    class BulkCleanup:
        def __init__(self, client, headers):
            self.client = client
            self.headers = headers
            self._items = []

        def add(self, obj_type, obj_id):
            self._items.append((obj_type, obj_id))

        def remove(self, obj_type, obj_id):
            try:
                self._items.remove((obj_type, obj_id))
            except ValueError:
                pass

        def get_items(self):
            return list(self._items)

    cleanup = BulkCleanup(api_client, admin_headers)
    yield cleanup

    for obj_type, obj_id in reversed(cleanup.get_items()):
        try:
            cleanup.client.delete(
                f'/api/v2/bo/{obj_type}/{obj_id}',
                headers=cleanup.headers
            )
        except Exception:
            pass


# ==================== 测试数据 Fixtures ====================

@pytest.fixture
def random_suffix():
    """
    [FIXTURE] 随机后缀
    [DESCRIPTION] 生成唯一标识符
    [RETURN] str: 8 字符十六进制字符串
    """
    return os.urandom(4).hex()


@pytest.fixture
def timestamp():
    """
    [FIXTURE] 时间戳
    [DESCRIPTION] 生成基于时间的唯一标识符
    [RETURN] int: 毫秒级时间戳
    """
    return int(time.time() * 1000)


@pytest.fixture
def unique_name(random_suffix):
    """
    [FIXTURE] 唯一名称
    [DESCRIPTION] 生成带随机后缀的名称
    [USAGE]
        username = unique_name('test_user')
        # 返回: 'test_user_a1b2c3d4'
    """
    def _unique_name(prefix=''):
        return f'{prefix}_{random_suffix}' if prefix else random_suffix
    return _unique_name


@pytest.fixture
def test_data_factory(random_suffix):
    """
    [FIXTURE] 测试数据工厂
    [DESCRIPTION] 生成标准格式的测试数据
    [USAGE]
        data = test_data_factory('user', username='test', email='test@test.com')
    """
    def _factory(obj_type, **kwargs):
        base_data = {
            'user': {
                'username': f'user_{random_suffix}',
                'password': 'test123',
                'email': f'{random_suffix}@test.com',
            },
            'role': {
                'code': f'role_{random_suffix}',
                'name': f'Role {random_suffix}',
            },
            'domain': {
                'code': f'domain_{random_suffix}',
                'name': f'Domain {random_suffix}',
            },
            'enum_type': {
                'code': f'enum_{random_suffix}',
                'name': f'Enum {random_suffix}',
            },
        }

        data = base_data.get(obj_type, {'code': f'{obj_type}_{random_suffix}'})
        data.update(kwargs)
        return data

    return _factory


# ==================== CRUD 操作 Fixtures ====================

@pytest.fixture
def create_object(api_client, admin_headers):
    """
    [FIXTURE] 创建对象的辅助函数
    [DESCRIPTION] 简化创建对象的测试代码
    [RETURN] function: (obj_type, data) -> (obj_id, response_data)
    """
    def _create(obj_type, data):
        resp = api_client.post(
            f'/api/v2/bo/{obj_type}',
            data=json.dumps(data),
            headers=admin_headers
        )
        resp_data = json.loads(resp.data)
        obj_id = None

        if resp.status_code in [200, 201] and resp_data.get('success'):
            obj_id = resp_data.get('data', {}).get('id')

        return obj_id, resp_data

    return _create


@pytest.fixture
def create_test_object(api_client, admin_headers, cleanup_tracker):
    """
    [FIXTURE] 创建测试对象（自动跟踪清理）
    [DESCRIPTION] 创建对象并自动添加到 cleanup_tracker
    [RETURN] function: (obj_type, data) -> obj_id
    """
    def _create(obj_type, data):
        resp = api_client.post(
            f'/api/v2/bo/{obj_type}',
            data=json.dumps(data),
            headers=admin_headers
        )
        resp_data = json.loads(resp.data)

        if resp.status_code in [200, 201] and resp_data.get('success'):
            obj_id = resp_data.get('data', {}).get('id')
            if obj_id:
                cleanup_tracker.append((obj_type, obj_id))
            return obj_id

        return None

    return _create


@pytest.fixture
def read_object(api_client, admin_headers):
    """
    [FIXTURE] 读取对象的辅助函数
    [DESCRIPTION] 简化读取对象的测试代码
    [RETURN] function: (obj_type, obj_id) -> response_data
    """
    def _read(obj_type, obj_id):
        resp = api_client.get(
            f'/api/v2/bo/{obj_type}/{obj_id}',
            headers=admin_headers
        )
        return json.loads(resp.data)

    return _read


@pytest.fixture
def update_object(api_client, admin_headers):
    """
    [FIXTURE] 更新对象的辅助函数
    [DESCRIPTION] 简化更新对象的测试代码
    [RETURN] function: (obj_type, obj_id, data) -> response_data
    """
    def _update(obj_type, obj_id, data):
        resp = api_client.put(
            f'/api/v2/bo/{obj_type}/{obj_id}',
            data=json.dumps(data),
            headers=admin_headers
        )
        return json.loads(resp.data)

    return _update


@pytest.fixture
def delete_object(api_client, admin_headers):
    """
    [FIXTURE] 删除对象的辅助函数
    [DESCRIPTION] 简化删除对象的测试代码
    [RETURN] function: (obj_type, obj_id) -> response_data
    """
    def _delete(obj_type, obj_id):
        resp = api_client.delete(
            f'/api/v2/bo/{obj_type}/{obj_id}',
            headers=admin_headers
        )
        return json.loads(resp.data) if resp.data else {}

    return _delete


# ==================== 查询 Fixtures ====================

@pytest.fixture
def list_objects(api_client, admin_headers):
    """
    [FIXTURE] 列出对象的辅助函数
    [DESCRIPTION] 简化列表查询的测试代码
    [RETURN] function: (obj_type, **kwargs) -> response_data
    [USAGE]
        resp = list_objects('user', page=1, page_size=10, ordering='-id')
    """
    def _list(obj_type, **kwargs):
        params = '&'.join([f'{k}={v}' for k, v in kwargs.items()])
        url = f'/api/v2/bo/{obj_type}'
        if params:
            url += f'?{params}'

        resp = api_client.get(url, headers=admin_headers)
        return json.loads(resp.data)

    return _list


# ==================== 导出 ====================

__all__ = [
    'cleanup_tracker',
    'cleanup_list',
    'bulk_cleanup',
    'random_suffix',
    'timestamp',
    'unique_name',
    'test_data_factory',
    'create_object',
    'create_test_object',
    'read_object',
    'update_object',
    'delete_object',
    'list_objects',
]
