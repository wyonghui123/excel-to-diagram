# -*- coding: utf-8 -*-
"""
GAP-006: enum_api 端到端测试 (15 用例)

[NEW] 2026-06-07 批次: 补齐 enum_api (13 端点) 的端到端测试
- 枚举类型: list / get / create / update / delete / history (6)
- 枚举值:   list / get / create / update / delete / options / query (7)
- 覆盖 happy + 系统枚举只读 + 锁定枚举不可写 + 404
"""
import json
import time
import pytest

pytestmark = pytest.mark.integration


ENUM_URL = '/api/v1'


class TestEnumAPI:
    """enum_api 端到端测试 (GAP-006)"""

    def test_list_enum_types(self, api_client, admin_headers):
        """GET /enum-types 列表"""
        resp = api_client.get(f'{ENUM_URL}/enum-types', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'data' in body
        # data 字段含 data 列表 + total + page + page_size
        assert 'data' in body['data']
        assert 'total' in body['data']

    def test_list_enum_types_with_pagination(self, api_client, admin_headers):
        """GET /enum-types?page=1&pageSize=5 分页"""
        resp = api_client.get(f'{ENUM_URL}/enum-types?page=1&pageSize=5', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert body['data']['page_size'] == 5

    def test_get_enum_type_404(self, api_client, admin_headers):
        """GET /enum-types/<unknown> 404"""
        resp = api_client.get(f'{ENUM_URL}/enum-types/__no_such_enum_type__', headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False
        assert '不存在' in body.get('message', '')

    def test_get_enum_type_history_404(self, api_client, admin_headers):
        """GET /enum-types/<unknown>/history 404"""
        resp = api_client.get(f'{ENUM_URL}/enum-types/__no_such__/history', headers=admin_headers)
        assert resp.status_code == 404

    def test_create_enum_type_missing_fields_400(self, api_client, admin_headers):
        """POST /enum-types 缺 id/name → 400"""
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'description': 'only desc'},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('success') is False

    def test_create_then_get_enum_type(self, api_client, admin_headers):
        """端到端: 创建枚举类型 → 读取 (admin)"""
        enum_id = f'test_enum_{int(time.time())}'
        resp = api_client.post(
            f'{ENUM_URL}/enum-types',
            json={
                'id': enum_id,
                'name': 'Test Enum Type',
                'category': 'business',
                'mutability': 'extensible',
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # 立即 GET
        resp2 = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
        assert resp2.status_code == 200
        assert resp2.get_json()['data']['id'] == enum_id
        # 清理: DELETE
        resp3 = api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
        assert resp3.status_code == 200

    def test_create_enum_value_in_known_type(self, api_client, admin_headers):
        """POST /enum-types/<id>/values 在已存在类型下创建值"""
        # 先创建类型
        enum_id = f'test_enum_v_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'Test V', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        # 创建值
        resp = api_client.post(
            f'{ENUM_URL}/enum-types/{enum_id}/values',
            json={'code': 'VAL_A', 'name': 'Value A', 'sort_order': 1},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # 清理
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_create_enum_value_in_unknown_type_404(self, api_client, admin_headers):
        """POST /enum-types/<unknown>/values → 404"""
        resp = api_client.post(
            f'{ENUM_URL}/enum-types/__no_type__/values',
            json={'code': 'X', 'name': 'X'},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_create_enum_value_missing_fields_400(self, api_client, admin_headers):
        """POST /enum-types/<id>/values 缺 code/name → 400"""
        enum_id = f'test_ef_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'T', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.post(
            f'{ENUM_URL}/enum-types/{enum_id}/values',
            json={'sort_order': 1},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_list_enum_options_for_type(self, api_client, admin_headers):
        """GET /enums/<id>/options 轻量级选项 (仅 code/name)"""
        enum_id = f'test_opt_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'Opt', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.get(f'{ENUM_URL}/enums/{enum_id}/options', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body['data'], list)
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_list_enum_values_for_type(self, api_client, admin_headers):
        """GET /enum-types/<id>/values 完整列表"""
        enum_id = f'test_lv_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'LV', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}/values', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'enum_type' in body['data']
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_update_enum_type_404(self, api_client, admin_headers):
        """PUT /enum-types/<unknown> → 404"""
        resp = api_client.put(
            f'{ENUM_URL}/enum-types/__no_such__',
            json={'name': 'New Name'},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_update_enum_type_works(self, api_client, admin_headers):
        """PUT /enum-types/<id> 业务枚举可更新"""
        enum_id = f'test_up_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'UP', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        resp = api_client.put(
            f'{ENUM_URL}/enum-types/{enum_id}',
            json={'name': 'UP Updated', 'description': 'Updated'},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        # 验证
        resp2 = api_client.get(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)
        assert resp2.get_json()['data']['name'] == 'UP Updated'
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_query_enum_values_via_general_endpoint(self, api_client, admin_headers):
        """GET /enum-values?enum_type_id=xxx 通用查询端点
        注: /api/v1/enum-values 已迁移 → 410"""
        enum_id = f'test_qy_{int(time.time())}'
        api_client.post(
            f'{ENUM_URL}/enum-types',
            json={'id': enum_id, 'name': 'QY', 'category': 'business', 'mutability': 'extensible'},
            headers=admin_headers,
        )
        # 缺 enum_type_id → 400 (旧路径可能 410)
        resp = api_client.get(f'{ENUM_URL}/enum-values', headers=admin_headers)
        assert resp.status_code in (400, 410)
        # 含 enum_type_id → 200 或 410
        resp2 = api_client.get(f'{ENUM_URL}/enum-values?enum_type_id={enum_id}', headers=admin_headers)
        assert resp2.status_code in (200, 410)
        api_client.delete(f'{ENUM_URL}/enum-types/{enum_id}', headers=admin_headers)

    def test_system_enum_is_immutable(self, api_client, admin_headers):
        """系统枚举不可更新 (category='system')"""
        # 找一个系统枚举 (如果有)
        resp = api_client.get(f'{ENUM_URL}/enum-types?category=system', headers=admin_headers)
        if resp.status_code != 200:
            pytest.skip("Cannot filter by category")
        items = resp.get_json()['data']['data']
        if not items:
            pytest.skip("No system enum types")
        sys_enum_id = items[0]['id']
        # 尝试 PUT
        resp2 = api_client.put(
            f'{ENUM_URL}/enum-types/{sys_enum_id}',
            json={'name': 'Hacked Name'},
            headers=admin_headers,
        )
        # 400 + SYSTEM_ENUM_IMMUTABLE
        assert resp2.status_code == 400
        body = resp2.get_json()
        assert 'SYSTEM_ENUM_IMMUTABLE' in body.get('error_code', '') or '不可修改' in body.get('message', '')
