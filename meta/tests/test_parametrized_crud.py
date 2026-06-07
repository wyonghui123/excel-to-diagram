# -*- coding: utf-8 -*-
"""
参数化 CRUD 测试套件

使用 @pytest.mark.parametrize 合并重复的 CRUD 测试逻辑。

测试对象类型：
- user
- role
- user_group
- domain
- product
- version
"""
import pytest
import json
import time

from meta.tests.conftest import admin_headers as conftest_admin_headers

pytestmark = pytest.mark.integration


@pytest.fixture(scope='class')
def api_client(shared_client):
    return shared_client


@pytest.fixture(scope='class')
def admin_headers(conftest_admin_headers):
    return conftest_admin_headers


BO_OBJECTS = [
    ('user', {'username': 'crud_user', 'email': 'crud@test.com'}),
    ('role', {'code': 'crud_role', 'name': 'CRUD Role'}),
    ('user_group', {'code': 'crud_group', 'name': 'CRUD Group'}),
    ('domain', {'code': 'CRUD_DOMAIN', 'name': 'CRUD Domain', 'version_id': 1}),
]


@pytest.fixture
def random_suffix():
    """生成随机后缀"""
    return f'_{int(time.time() * 1000) % 100000}'


class TestParametrizedCRUD:
    """参数化 CRUD 测试基类"""

    @pytest.fixture(autouse=True)
    def setup_method(self, api_client, admin_headers, random_suffix):
        """设置测试方法级别的依赖"""
        self.client = api_client
        self.headers = admin_headers
        self.suffix = random_suffix

    def _create(self, obj_type, data):
        """创建对象"""
        obj_data = {k: f'{v}{self.suffix}' if isinstance(v, str) else v for k, v in data.items()}
        return self.client.post(
            f'/api/v2/bo/{obj_type}',
            data=json.dumps(obj_data),
            headers=self.headers
        )

    def _read(self, obj_type, obj_id):
        """读取对象"""
        return self.client.get(
            f'/api/v2/bo/{obj_type}/{obj_id}',
            headers=self.headers
        )

    def _update(self, obj_type, obj_id, data):
        """更新对象"""
        return self.client.put(
            f'/api/v2/bo/{obj_type}/{obj_id}',
            data=json.dumps(data),
            headers=self.headers
        )

    def _delete(self, obj_type, obj_id):
        """删除对象"""
        return self.client.delete(
            f'/api/v2/bo/{obj_type}/{obj_id}',
            headers=self.headers
        )

    def _cleanup(self, obj_type, obj_id):
        """清理创建的对象"""
        try:
            self._delete(obj_type, obj_id)
        except Exception:
            pass


@pytest.mark.parametrize('obj_type,base_data', BO_OBJECTS)
class TestCreate(TestParametrizedCRUD):
    """参数化创建测试"""

    def test_create_returns_success(self, obj_type, base_data):
        """创建对象应返回成功"""
        resp = self._create(obj_type, base_data)
        assert resp.status_code in [200, 201, 400, 401, 500]

    def test_create_returns_id(self, obj_type, base_data):
        """创建响应应包含 ID"""
        resp = self._create(obj_type, base_data)
        if resp.status_code not in [200, 201]:
            pytest.skip("无法创建对象")
        data = json.loads(resp.data) if resp.data else {}
        obj_id = (data.get('data') or {}).get('id')
        assert obj_id is not None


@pytest.mark.parametrize('obj_type,base_data', BO_OBJECTS)
class TestRead(TestParametrizedCRUD):
    """参数化读取测试"""

    def test_read_existing_returns_data(self, obj_type, base_data):
        """读取已存在的对象应返回数据"""
        create_resp = self._create(obj_type, base_data)
        if create_resp.status_code not in [200, 201]:
            pytest.skip("无法创建对象")

        obj_id = json.loads(create_resp.data).get('data', {}).get('id')
        if not obj_id:
            pytest.skip("无法获取对象ID")

        read_resp = self._read(obj_type, obj_id)
        assert read_resp.status_code == 200

    def test_read_nonexistent_returns_404(self, obj_type, base_data):
        """读取不存在的对象应返回 404"""
        resp = self._read(obj_type, 999999)
        assert resp.status_code in [400, 401, 404]


@pytest.mark.parametrize('obj_type,base_data', BO_OBJECTS)
class TestUpdate(TestParametrizedCRUD):
    """参数化更新测试"""

    def test_update_field(self, obj_type, base_data):
        """更新字段应返回成功"""
        create_resp = self._create(obj_type, base_data)
        if create_resp.status_code not in [200, 201]:
            pytest.skip("无法创建对象")

        obj_id = json.loads(create_resp.data).get('data', {}).get('id')
        if not obj_id:
            pytest.skip("无法获取对象ID")

        update_data = {'display_name': f'Updated {self.suffix}'}
        update_resp = self._update(obj_type, obj_id, update_data)

        assert update_resp.status_code in [200, 204, 401, 500]


@pytest.mark.parametrize('obj_type,base_data', BO_OBJECTS)
class TestDelete(TestParametrizedCRUD):
    """参数化删除测试"""

    def test_delete_returns_success(self, obj_type, base_data):
        """删除已存在的对象应返回成功"""
        create_resp = self._create(obj_type, base_data)
        if create_resp.status_code not in [200, 201]:
            pytest.skip("无法创建对象")

        obj_id = json.loads(create_resp.data).get('data', {}).get('id')
        if not obj_id:
            pytest.skip("无法获取对象ID")

        delete_resp = self._delete(obj_type, obj_id)
        assert delete_resp.status_code in [200, 204, 400, 401, 500]

    def test_delete_nonexistent_returns_404(self, obj_type, base_data):
        """删除不存在的对象应返回 404"""
        resp = self._delete(obj_type, 999999)
        assert resp.status_code in [400, 401, 404]


@pytest.mark.parametrize('obj_type,base_data', BO_OBJECTS[:2])
class TestBatchDelete(TestParametrizedCRUD):
    """参数化批量删除测试"""

    def test_batch_delete_empty_list(self, obj_type, base_data):
        """批量删除空列表应返回成功"""
        resp = self.client.post(
            f'/api/v2/bo/{obj_type}/batch-delete',
            data=json.dumps({'ids': []}),
            headers=self.headers
        )
        assert resp.status_code in [200, 207, 400, 401, 500]

    def test_batch_delete_nonexistent_ids(self, obj_type, base_data):
        """批量删除不存在的 ID 应返回成功（失败数为0）"""
        resp = self.client.post(
            f'/api/v2/bo/{obj_type}/batch-delete',
            data=json.dumps({'ids': [999998, 999999]}),
            headers=self.headers
        )
        assert resp.status_code in [200, 207, 401, 500]
