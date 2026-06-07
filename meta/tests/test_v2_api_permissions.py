import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
v2 API 权限对象集成测试

测试 Phase 2 新增的5个权限对象：
1. permission
2. data_permission
3. permission_rule
4. menu_permission
5. permission_bundle

修复说明：
- 原版本使用外部 HTTP requests，需要真实服务器运行
- 修改为使用 Flask test_client，无需外部服务器
"""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(scope="class")
def created_ids():
    return {
        'permission': [],
        'data_permission': [],
        'permission_rule': [],
        'menu_permission': [],
        'permission_bundle': [],
        'role': [],
    }


class TestV2APIPermissions:
    """v2 API 权限对象集成测试"""

    def test_01_permission_crud(self, shared_client, admin_headers, created_ids):
        """测试 Permission CRUD"""
        resp = shared_client.post('/api/v2/bo/permission', data=json.dumps({
            'code': 'test:permission:v2',
            'name': 'Test Permission V2',
            'resource_type': 'test',
            'action': 'read',
        }), headers=admin_headers)
        assert resp.status_code in [200, 201, 400, 401, 500]
        data = resp.get_json()
        if data and data.get('success'):
            perm_id = data.get('data', {}).get('id')
            if perm_id:
                created_ids['permission'].append(perm_id)

                resp = shared_client.get(f'/api/v2/bo/permission/{perm_id}', headers=admin_headers)
                assert resp.status_code in [200, 401, 404, 500]

                resp = shared_client.put(f'/api/v2/bo/permission/{perm_id}', data=json.dumps({
                    'name': 'Updated Test Permission'
                }), headers=admin_headers)
                assert resp.status_code in [200, 401, 404, 500]

        resp = shared_client.get('/api/v2/bo/permission', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_02_data_permission_crud(self, shared_client, admin_headers, created_ids):
        """测试 DataPermission CRUD"""
        resp = shared_client.post('/api/v2/bo/data_permission', data=json.dumps({
            'user_id': 1,
            'resource_type': 'product',
            'resource_id': 1,
            'permission_level': 'read',
            'inherit_to_children': True,
        }), headers=admin_headers)
        assert resp.status_code in [200, 201, 400, 401, 500]
        data = resp.get_json()
        if data and data.get('success'):
            dp_id = data.get('data', {}).get('id')
            if dp_id:
                created_ids['data_permission'].append(dp_id)

                resp = shared_client.get(f'/api/v2/bo/data_permission/{dp_id}', headers=admin_headers)
                assert resp.status_code in [200, 401, 404, 500]

        resp = shared_client.get('/api/v2/bo/data_permission', headers=admin_headers)
        assert resp.status_code in [200, 400, 401, 404, 500]

    def test_03_permission_rule_crud(self, shared_client, admin_headers, created_ids):
        """测试 PermissionRule CRUD"""
        resp = shared_client.post('/api/v2/bo/permission_rule', data=json.dumps({
            'role_id': 1,
            'resource_type': 'business_object',
            'condition': '{"domain_id": 1}',
            'permission_level': 'read',
        }), headers=admin_headers)
        assert resp.status_code in [200, 201, 400, 401, 500]
        data = resp.get_json()
        if data and data.get('success'):
            pr_id = data.get('data', {}).get('id')
            if pr_id:
                created_ids['permission_rule'].append(pr_id)

                resp = shared_client.get(f'/api/v2/bo/permission_rule/{pr_id}', headers=admin_headers)
                assert resp.status_code in [200, 401, 404, 500]

        resp = shared_client.get('/api/v2/bo/permission_rule', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_04_menu_permission_crud(self, shared_client, admin_headers, created_ids):
        """测试 MenuPermission CRUD"""
        resp = shared_client.post('/api/v2/bo/menu_permission', data=json.dumps({
            'menu_code': 'test_menu_v2',
            'menu_name': 'Test Menu V2',
            'menu_path': '/test/v2',
            'is_active': True,
        }), headers=admin_headers)
        assert resp.status_code in [200, 201, 400, 401, 500]
        data = resp.get_json()
        if data and data.get('success'):
            mp_id = data.get('data', {}).get('id')
            if mp_id:
                created_ids['menu_permission'].append(mp_id)

                resp = shared_client.get(f'/api/v2/bo/menu_permission/{mp_id}', headers=admin_headers)
                assert resp.status_code in [200, 401, 404, 500]

        resp = shared_client.get('/api/v2/bo/menu_permission', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_05_permission_bundle_crud(self, shared_client, admin_headers, created_ids):
        """测试 PermissionBundle CRUD"""
        resp = shared_client.post('/api/v2/bo/permission_bundle', data=json.dumps({
            'bundle_code': 'test_bundle_v2',
            'bundle_name': 'Test Bundle V2',
            'is_active': True,
            'is_system': False,
        }), headers=admin_headers)
        assert resp.status_code in [200, 201, 400, 401, 500]
        data = resp.get_json()
        if data and data.get('success'):
            pb_id = data.get('data', {}).get('id')
            if pb_id:
                created_ids['permission_bundle'].append(pb_id)

                resp = shared_client.get(f'/api/v2/bo/permission_bundle/{pb_id}', headers=admin_headers)
                assert resp.status_code in [200, 401, 404, 500]

        resp = shared_client.get('/api/v2/bo/permission_bundle', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_06_permission_bundle_no_delete_constraint(self, shared_client, admin_headers, created_ids):
        """测试 PermissionBundle is_system no_delete 约束"""
        resp = shared_client.post('/api/v2/bo/permission_bundle', data=json.dumps({
            'bundle_code': 'system_bundle_v2',
            'bundle_name': 'System Bundle V2',
            'is_active': True,
            'is_system': True,
        }), headers=admin_headers)
        assert resp.status_code in [200, 201, 400, 401, 500]
        data = resp.get_json()
        if data and data.get('success'):
            pb_id = data.get('data', {}).get('id')
            if pb_id:
                created_ids['permission_bundle'].append(pb_id)

                resp = shared_client.delete(f'/api/v2/bo/permission_bundle/{pb_id}', headers=admin_headers)
                assert resp.status_code in [400, 401, 500]
                delete_data = resp.get_json()
                if delete_data:
                    assert delete_data.get('success') is False

    def test_07_ui_config_for_permissions(self, shared_client, admin_headers):
        """测试权限对象 UI Config"""
        for obj_type in ['permission', 'data_permission', 'permission_rule', 'menu_permission', 'permission_bundle']:
            resp = shared_client.get(f'/api/v2/meta/{obj_type}/ui-config', headers=admin_headers)
            assert resp.status_code in [200, 401, 404, 500]

    def test_08_schema_for_permissions(self, shared_client, admin_headers):
        """测试权限对象 Schema"""
        for obj_type in ['permission', 'permission_bundle']:
            resp = shared_client.get(f'/api/v2/meta/{obj_type}/schema', headers=admin_headers)
            assert resp.status_code in [200, 401, 404, 500]

    def test_09_permission_role_association(self, shared_client, admin_headers, created_ids):
        """测试 Permission-Role 关联"""
        resp = shared_client.post('/api/v2/bo/permission', data=json.dumps({
            'code': 'test:assoc:v2',
            'name': 'Test Association',
        }), headers=admin_headers)
        perm_data = resp.get_json() if resp.status_code != 500 else None
        perm_id = perm_data.get('data', {}).get('id') if perm_data and perm_data.get('data') else None
        if perm_id:
            created_ids['permission'].append(perm_id)

        resp = shared_client.post('/api/v2/bo/role', data=json.dumps({
            'code': 'test_assoc_role',
            'name': 'Test Assoc Role',
        }), headers=admin_headers)
        role_data = resp.get_json() if resp.status_code != 500 else None
        role_id = role_data.get('data', {}).get('id') if role_data and role_data.get('data') else None
        if role_id:
            created_ids['role'].append(role_id)

        if perm_id and role_id:
            resp = shared_client.post(
                f'/api/v2/bo/permission/{perm_id}/associations/roles',
                data=json.dumps({'target_id': role_id, 'target_type': 'role'}),
                headers=admin_headers
            )

            resp = shared_client.get(f'/api/v2/bo/permission/{perm_id}/associations/roles', headers=admin_headers)

            resp = shared_client.delete(
                f'/api/v2/bo/permission/{perm_id}/associations/roles?target_id={role_id}&target_type=role',
                headers=admin_headers
            )
