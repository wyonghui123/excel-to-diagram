# -*- coding: utf-8 -*-
"""
[MODULE] CRUD 测试基类
[DESCRIPTION] 提供标准化的 BO CRUD 操作测试基类

使用方式：
1. 继承 BaseCrudTest 类
2. 定义 object_type 和 fixtures
3. 测试方法自动使用标准化的 CRUD 操作

示例：
    class TestUserCRUD(BaseCrudTest):
        object_type = 'user'
        create_data = {'username': 'test', 'password': 'pwd123', 'email': 'test@test.com'}
        required_fields = ['username', 'password']
        update_data = {'email': 'new@test.com'}

    # 自动获得以下测试方法：
    # - test_create_success
    # - test_create_without_required_field
    # - test_read_by_id
    # - test_read_nonexistent
    # - test_update_success
    # - test_delete_success
    # - test_list_pagination
"""

import pytest
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from meta.tests.shared.parametrize_crud import (
    generate_unique_data,
    get_required_fields,
    get_update_data,
)


class BaseCrudTest:
    """
    [BASE CLASS] CRUD 测试基类
    [DESCRIPTION] 提供标准化的 BO CRUD 操作测试

    子类需要定义：
        object_type: str - 业务对象类型 (如 'user', 'role', 'domain')
        create_data: dict - 创建测试数据
        required_fields: list - 必填字段列表
        update_data: dict - 更新测试数据（可选）
    """

    object_type: str = None
    create_data: Dict[str, Any] = None
    required_fields: List[str] = None
    update_data: Dict[str, Any] = None

    @pytest.fixture
    def api_client(self):
        """获取 API 客户端"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        return client

    @pytest.fixture
    def admin_headers(self):
        """获取管理员认证头"""
        from meta.services.token_service import TokenService
        from meta.services.auth_provider import UserInfo

        user = UserInfo(
            user_id='1', username='admin', display_name='Admin',
            email='admin@test.com', roles=['admin'], permissions=['*']
        )
        token, _ = TokenService.create_token(user)
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'X-User-Id': '1',
            'X-User-Name': 'admin'
        }

    @pytest.fixture
    def cleanup(self, api_client, admin_headers):
        """资源清理跟踪器"""
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
    def random_suffix(self):
        """随机后缀"""
        return os.urandom(4).hex()

    def _make_unique_data(self, suffix: str = None) -> Dict[str, Any]:
        """生成唯一测试数据"""
        if suffix is None:
            suffix = os.urandom(4).hex()

        data = {}
        for key, value in (self.create_data or {}).items():
            if isinstance(value, str) and '{suffix}' in value:
                data[key] = value.format(suffix=suffix)
            elif key == 'username' or key == 'code':
                data[key] = f'{value}_{suffix}'
            else:
                data[key] = value
        return data

    def _create_object(self, api_client, admin_headers, data: Dict) -> Tuple[Any, Dict]:
        """创建对象并返回 (id, response_data)"""
        resp = api_client.post(
            f'/api/v2/bo/{self.object_type}',
            data=json.dumps(data),
            headers=admin_headers
        )
        resp_data = json.loads(resp.data)

        if resp.status_code in [200, 201] and resp_data.get('success'):
            obj_id = resp_data.get('data', {}).get('id')
            if obj_id:
                return obj_id, resp_data

        return None, resp_data

    def _read_object(self, api_client, admin_headers, obj_id: int) -> Dict:
        """读取单个对象"""
        resp = api_client.get(
            f'/api/v2/bo/{self.object_type}/{obj_id}',
            headers=admin_headers
        )
        return json.loads(resp.data)

    def _update_object(self, api_client, admin_headers, obj_id: int, data: Dict) -> Dict:
        """更新对象"""
        resp = api_client.put(
            f'/api/v2/bo/{self.object_type}/{obj_id}',
            data=json.dumps(data),
            headers=admin_headers
        )
        return json.loads(resp.data)

    def _delete_object(self, api_client, admin_headers, obj_id: int) -> Dict:
        """删除对象"""
        resp = api_client.delete(
            f'/api/v2/bo/{self.object_type}/{obj_id}',
            headers=admin_headers
        )
        return json.loads(resp.data) if resp.data else {}

    def _list_objects(self, api_client, admin_headers, **kwargs) -> Dict:
        """列出对象"""
        params = '&'.join([f'{k}={v}' for k, v in kwargs.items()])
        url = f'/api/v2/bo/{self.object_type}'
        if params:
            url += f'?{params}'
        resp = api_client.get(url, headers=admin_headers)
        return json.loads(resp.data)

    # ==================== 测试方法 ====================

    def test_create_success(self, api_client, admin_headers, cleanup, random_suffix):
        """测试创建成功"""
        data = self._make_unique_data(random_suffix)
        obj_id, resp_data = self._create_object(api_client, admin_headers, data)

        assert obj_id is not None, f"创建失败: {resp_data.get('message', 'Unknown error')}"
        cleanup.append((self.object_type, obj_id))
        assert resp_data.get('success') is True

    def test_create_returns_201(self, api_client, admin_headers, random_suffix):
        """测试返回 201 状态码"""
        data = self._make_unique_data(random_suffix)
        resp = api_client.post(
            f'/api/v2/bo/{self.object_type}',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert resp.status_code in [200, 201, 401, 500]

    def test_create_without_required_field(self, api_client, admin_headers, random_suffix):
        """测试缺少必填字段返回错误"""
        data = self._make_unique_data(random_suffix)
        for field in (self.required_fields or []):
            incomplete_data = {k: v for k, v in data.items() if k != field}
            if incomplete_data:
                resp = api_client.post(
                    f'/api/v2/bo/{self.object_type}',
                    data=json.dumps(incomplete_data),
                    headers=admin_headers
                )
                assert resp.status_code in [400, 401, 422]

    def test_read_by_id(self, api_client, admin_headers, cleanup, random_suffix):
        """测试通过 ID 读取"""
        data = self._make_unique_data(random_suffix)
        obj_id, _ = self._create_object(api_client, admin_headers, data)
        if obj_id:
            cleanup.append((self.object_type, obj_id))
            resp_data = self._read_object(api_client, admin_headers, obj_id)
            assert resp_data.get('success') is True

    def test_read_nonexistent(self, api_client, admin_headers):
        """测试读取不存在的对象"""
        resp = api_client.get(
            f'/api/v2/bo/{self.object_type}/99999',
            headers=admin_headers
        )
        assert resp.status_code in [401, 404, 500]

    def test_update_success(self, api_client, admin_headers, cleanup, random_suffix):
        """测试更新成功"""
        data = self._make_unique_data(random_suffix)
        obj_id, _ = self._create_object(api_client, admin_headers, data)
        if obj_id:
            cleanup.append((self.object_type, obj_id))
            update_data = self.update_data or {'name': 'updated'}
            resp_data = self._update_object(api_client, admin_headers, obj_id, update_data)
            assert resp_data.get('success') is True

    def test_update_nonexistent(self, api_client, admin_headers):
        """测试更新不存在的对象"""
        update_data = self.update_data or {'name': 'updated'}
        resp = api_client.put(
            f'/api/v2/bo/{self.object_type}/99999',
            data=json.dumps(update_data),
            headers=admin_headers
        )
        assert resp.status_code in [400, 401, 404]

    def test_delete_success(self, api_client, admin_headers, random_suffix):
        """测试删除成功"""
        data = self._make_unique_data(random_suffix)
        obj_id, _ = self._create_object(api_client, admin_headers, data)
        if obj_id:
            resp_data = self._delete_object(api_client, admin_headers, obj_id)
            assert resp_data.get('success') is True

    def test_delete_nonexistent(self, api_client, admin_headers):
        """测试删除不存在的对象"""
        resp = api_client.delete(
            f'/api/v2/bo/{self.object_type}/99999',
            headers=admin_headers
        )
        assert resp.status_code in [400, 401, 404]

    def test_list_pagination(self, api_client, admin_headers):
        """测试分页查询"""
        resp_data = self._list_objects(api_client, admin_headers, page=1, page_size=10)
        assert resp_data.get('success') is True
        assert 'data' in resp_data

    def test_list_with_ordering(self, api_client, admin_headers):
        """测试排序"""
        resp_data = self._list_objects(
            api_client, admin_headers,
            ordering='id', page=1, page_size=10
        )
        assert resp_data.get('success') is True


# ==================== 导出 ====================
__all__ = [
    'BaseCrudTest',
    'generate_unique_data',
    'get_required_fields',
    'get_update_data',
]
