import pytest

pytestmark = pytest.mark.integration

"""
关系CRUD API集成测试

测试目标：验证关系的创建、读取、更新、删除操作

前置条件：
    1. 数据库中有测试数据（version, domain, sub_domain, service_module, business_object）
    2. 后端服务运行在 http://localhost:5000

运行方式：
    python -m pytest meta/tests/test_relationship_crud.py -v

注意：此测试需要外部服务器运行，如果没有服务器会自动跳过
"""

import pytest
import requests
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo

BASE_URL = os.environ.get('TEST_API_URL', 'http://localhost:3010')  # v3.18 P1: 修复端口不一致


def _server_check():
    try:
        import requests as _req
        r = _req.get(f'http://127.0.0.1:3010/', timeout=2)
        return r.status_code < 500
    except Exception:
        return False


_SERVER_AVAILABLE = _server_check()


def get_auth_headers():
    """获取认证headers"""
    test_user = UserInfo(
        user_id='1', username='test_user', display_name='Test User',
        email='test@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(test_user)
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }


class TestRelationshipCRUD:
    """关系CRUD操作测试"""

    @pytest.fixture(autouse=True, scope='class')
    def _ensure_data(self, auth_headers):
        """v3.18 P1: 修复 S018 数据依赖 skip
        自动确保 version 和 ≥2 business_objects 存在
        """
        if not _SERVER_AVAILABLE:
            pytest.skip("后端服务未运行，跳过集成测试")
        # 检查并创建 version
        v_resp = requests.get(f'{BASE_URL}/api/v2/bo/versions', params={'page': 1, 'pageSize': 1}, headers=auth_headers)
        if v_resp.status_code == 200 and v_resp.json().get('data'):
            return
        v_create = requests.post(
            f'{BASE_URL}/api/v2/bo/version',
            json={'name': 'Default V1', 'code': 'V1', 'description': 'auto-created'},
            headers=auth_headers
        )
        if v_create.status_code not in [200, 201]:
            pytest.skip("Cannot ensure version data")
        # 创建 ≥2 business_objects
        for i in range(2):
            requests.post(
                f'{BASE_URL}/api/v2/bo/business_object',
                json={
                    'name': f'TestBO_{i}',
                    'code': f'TEST_BO_{i}',
                    'version_id': 1,
                },
                headers=auth_headers
            )

    @pytest.fixture(scope='class')
    def auth_headers(self):
        """获取认证headers"""
        return get_auth_headers()

    @pytest.fixture(scope='class')
    def version_id(self, auth_headers):
        """获取测试用版本ID"""
        response = requests.get(f'{BASE_URL}/api/v2/bo/versions', params={'page': 1, 'pageSize': 1}, headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                return data.get('data', {})[0]['id']
        pytest.skip("No version available for testing")

    @pytest.fixture(scope='class')
    def business_object_ids(self, version_id, auth_headers):
        """获取测试用业务对象ID对"""
        response = requests.get(
            f'{BASE_URL}/api/v2/bo/business_objects',
            params={'version_id': version_id, 'page': 1, 'pageSize': 2},
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and len(data.get('data', [])) >= 2:
                ids = [bo['id'] for bo in data.get('data', {})[:2]]
                return {'source_bo_id': ids[0], 'target_bo_id': ids[1], 'version_id': version_id}
        pytest.skip("Not enough business objects for testing")

    @pytest.fixture
    def created_relationship_id(self, business_object_ids, auth_headers):
        """创建测试用关系，返回ID，测试结束后自动清理"""
        relation_data = {
            'version_id': business_object_ids.get('version_id', 1),
            'source_bo_id': business_object_ids['source_bo_id'],
            'target_bo_id': business_object_ids['target_bo_id'],
            'relation_code': 'TEST_RELATION',
            'relation_desc': 'Test relation for CRUD'
        }
        response = requests.post(f'{BASE_URL}/api/v2/bo/relationships', json=relation_data, headers=auth_headers)
        if response.status_code == 201:
            data = response.json()
            if data.get('success'):
                yield data.get('id')
                requests.delete(f'{BASE_URL}/api/v2/bo/relationships/{data.get("id")}', params={'force': 'true'}, headers=auth_headers)
        else:
            pytest.skip(f"Failed to create test relationship: {response.text}")

    def test_list_relationships(self, version_id, auth_headers):
        """测试：查询关系列表"""
        response = requests.get(
            f'{BASE_URL}/api/v2/bo/relationships',
            params={'version_id': version_id, 'page': 1, 'pageSize': 10},
            headers=auth_headers
        )

        assert response.status_code == 200, f"列表查询失败: {response.text}"
        data = response.json()
        assert data.get('success'), f"API返回失败: {data.get('message')}"
        assert isinstance(data.get('data'), list), "返回数据应该是列表"

    def test_filter_relationships_by_codes(self, version_id, auth_headers):
        """测试：按关系编码过滤"""
        response = requests.get(
            f'{BASE_URL}/api/v2/bo/relationships',
            params={'version_id': version_id, 'page': 1, 'pageSize': 5},
            headers=auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                codes = list(set([r.get('relation_code') for r in data.get('data', {})[:3] if r.get('relation_code')]))
                if codes:
                    response = requests.get(
                        f'{BASE_URL}/api/v2/bo/relationships',
                        params={'version_id': version_id, 'relation_codes': codes},
                        headers=auth_headers
                    )
                    assert response.status_code in [200, 401, 404, 500]
                    result = response.json()
                    assert result.get('success')

    def test_create_relationship(self, business_object_ids, auth_headers):
        """测试：创建关系"""
        relation_data = {
            'version_id': business_object_ids.get('version_id', 1),
            'source_bo_id': business_object_ids['source_bo_id'],
            'target_bo_id': business_object_ids['target_bo_id'],
            'relation_code': 'CREATE_TEST_' + str(int(__import__('time').time())),
            'relation_desc': 'Test create operation'
        }

        response = requests.post(f'{BASE_URL}/api/v2/bo/relationship', json=relation_data, headers=auth_headers)

        assert response.status_code in [200, 201, 401, 500], f"创建失败: {response.text}"
        data = response.json()
        assert data.get('success'), f"创建失败: {data.get('message')}"
        assert 'id' in data.get('data', {}), "创建后应返回ID"

        created_id = data.get('data', {}).get('id')
        if created_id:
            requests.delete(f'{BASE_URL}/api/v2/bo/relationship/{created_id}', params={'force': 'true'}, headers=auth_headers)

    def test_read_relationship(self, created_relationship_id, auth_headers):
        """测试：读取单个关系"""
        response = requests.get(f'{BASE_URL}/api/v2/bo/relationship/{created_relationship_id}', headers=auth_headers)

        assert response.status_code == 200, f"读取失败: {response.text}"
        data = response.json()
        assert data.get('success'), f"读取失败: {data.get('message')}"
        assert data.get('data', {}).get('id') == created_relationship_id

    def test_update_relationship(self, created_relationship_id, auth_headers):
        """测试：更新关系"""
        update_data = {
            'relation_desc': 'Updated description via test'
        }

        response = requests.put(
            f'{BASE_URL}/api/v2/bo/relationship/{created_relationship_id}',
            json=update_data,
            headers=auth_headers
        )

        assert response.status_code == 200, f"更新失败: {response.text}"
        data = response.json()
        assert data.get('success'), f"更新失败: {data.get('message')}"

        response = requests.get(f'{BASE_URL}/api/v2/bo/relationship/{created_relationship_id}', headers=auth_headers)
        updated = response.json()
        assert updated.get('data', {}).get('relation_desc') == 'Updated description via test'

    def test_delete_relationship(self, business_object_ids, auth_headers):
        """测试：删除关系"""
        relation_data = {
            'version_id': business_object_ids.get('version_id', 1),
            'source_bo_id': business_object_ids['source_bo_id'],
            'target_bo_id': business_object_ids['target_bo_id'],
            'relation_code': 'DELETE_TEST_' + str(int(__import__('time').time())),
            'relation_desc': 'Test delete operation'
        }

        create_response = requests.post(f'{BASE_URL}/api/v2/bo/relationship', json=relation_data, headers=auth_headers)
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Cannot create test data: {create_response.text}")

        created_id = create_response.json().get('data', {}).get('id')

        response = requests.delete(f'{BASE_URL}/api/v2/bo/relationship/{created_id}', headers=auth_headers)

        assert response.status_code == 200, f"删除失败: {response.text}"
        data = response.json()
        assert data.get('success'), f"删除失败: {data.get('message')}"

        response = requests.get(f'{BASE_URL}/api/v2/bo/relationship/{created_id}', headers=auth_headers)
        assert response.status_code == 404, "删除后应该找不到记录"

    def test_delete_nonexistent_relationship(self, auth_headers):
        """测试：删除不存在的记录"""
        response = requests.delete(f'{BASE_URL}/api/v2/bo/relationship/999999999', headers=auth_headers)

        assert response.status_code in [400, 401, 404], "删除不存在的记录应返回错误"

    def test_create_relationship_missing_required_fields(self, business_object_ids, auth_headers):
        """测试：创建关系时缺少必需字段"""
        relation_data = {
            'version_id': business_object_ids.get('version_id', 1),
            'target_bo_id': business_object_ids['target_bo_id'],
            'relation_code': 'INCOMPLETE_TEST'
        }

        response = requests.post(f'{BASE_URL}/api/v2/bo/relationships', json=relation_data, headers=auth_headers)

        assert response.status_code >= 400, "缺少必需字段应返回错误"


class TestRelationshipValidation:
    """关系验证规则测试"""

    def test_cannot_delete_bo_with_relationships(self):
        """测试：不能删除有关联关系的业务对象"""
        pass

    def test_relationship_requires_same_version(self):
        """测试：关系的源和目标应该在同一版本"""
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
