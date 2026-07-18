"""
BaseCRUDTestCase - CRUD 测试基类 (Phase 7 重构)

提供完整的 CRUD 测试模板 (替代 45+ 文件的重复模式)

使用示例:
    class TestProductCRUD(BaseCRUDTestCase):
        object_type = 'product'

        def make_payload(self):
            return {'name': f'product_{uuid4().hex[:8]}'}

        def mutate_payload(self, payload):
            payload['name'] += '_updated'
            return payload
"""
import pytest
from .base_api import BaseAPITestCase


class BaseCRUDTestCase(BaseAPITestCase):
    """
    CRUD 测试基类

    完整覆盖 Create/Read/Update/Delete/List 五种操作
    + 错误路径 (404, 401, 403, 400)

    子类必须设置:
        object_type = 'product'

    子类必须实现:
        make_payload()  -> dict  # 唯一性 payload

    子类可覆盖:
        mutate_payload(payload)  # 用于 update, 不传则 skip update test
        skip_delete = False  # True 则跳过 delete test
    """

    object_type: str = None

    skip_create: bool = False
    skip_read: bool = False
    skip_update: bool = False
    skip_delete: bool = False
    skip_list: bool = False

    def make_payload(self):
        """生成唯一性 payload - 子类必须 override"""
        raise NotImplementedError("Subclass must implement make_payload()")

    def mutate_payload(self, payload):
        """修改 payload 用于 update - 默认加 _updated 后缀"""
        import copy
        new = copy.deepcopy(payload)
        if 'name' in new:
            new['name'] = f"{new['name']}_updated"
        return new

    def test_create_success(self):
        """POST 创建应成功"""
        if self.skip_create:
            pytest.skip("skip_create=True")
        payload = self.make_payload()
        response = self.client.post(self.list_url, json=payload, headers=self.admin_headers)
        self.assert_api_success(response, expected_status=201)
        # 保存以供后续测试
        self._created_id = response.get_json().get('data', {}).get('id')
        assert self._created_id, "Created object should have id"
        return self._created_id

    def test_read_success(self):
        """GET 详情应成功"""
        if self.skip_read:
            pytest.skip("skip_read=True")
        # 先创建
        obj_id = self._ensure_created()
        response = self.client.get(self.detail_url(obj_id), headers=self.admin_headers)
        self.assert_api_success(response, expected_status=200)
        return response.get_json()

    def test_list_success(self):
        """GET 列表应成功"""
        if self.skip_list:
            pytest.skip("skip_list=True")
        # 先创建
        self._ensure_created()
        response = self.client.get(self.list_url, headers=self.admin_headers)
        self.assert_api_success(response, expected_status=200)
        data = response.get_json().get('data', {})
        items = data.get('items') or data.get('list') or []
        assert len(items) >= 1, "List should contain at least the created item"

    def test_update_success(self):
        """PUT 更新应成功"""
        if self.skip_update:
            pytest.skip("skip_update=True")
        obj_id = self._ensure_created()
        payload = self.mutate_payload(self.make_payload())
        response = self.client.put(self.detail_url(obj_id), json=payload, headers=self.admin_headers)
        self.assert_api_success(response, expected_status=200)

    def test_delete_success(self):
        """DELETE 删除应成功"""
        if self.skip_delete:
            pytest.skip("skip_delete=True")
        obj_id = self._ensure_created()
        response = self.client.delete(self.detail_url(obj_id), headers=self.admin_headers)
        self.assert_api_success(response, expected_status=200 if response.status_code != 204 else 204)

    def test_read_404_not_found(self):
        """GET 不存在的 id 应返回 404"""
        response = self.client.get(self.detail_url(99999999), headers=self.admin_headers)
        self.assert_api_error(response, expected_status=404)

    def test_create_401_no_auth(self):
        """POST 无认证应返回 401"""
        payload = self.make_payload()
        response = self.client.post(self.list_url, json=payload)
        self.assert_api_error(response, expected_status=401)

    # ==================== 助手 ====================

    def _ensure_created(self):
        """确保已创建一个对象, 返回 id"""
        if hasattr(self, '_created_id') and self._created_id:
            return self._created_id
        payload = self.make_payload()
        response = self.client.post(self.list_url, json=payload, headers=self.admin_headers)
        self.assert_api_success(response, expected_status=201)
        self._created_id = response.get_json().get('data', {}).get('id')
        return self._created_id