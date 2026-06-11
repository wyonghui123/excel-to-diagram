# -*- coding: utf-8 -*-
"""
V1 Cleanup - role.yaml 字段 + API 验证

依据: spec-auth-object-category-v2-2026-06-10.md FR-V1-001 + FR-V1-002
- role.yaml 不应再含 is_super_admin / priority 字段
- role API 不再返回这 2 字段
"""
import pytest
import yaml
import os


SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'schemas', 'role.yaml'
)


class TestRoleSchemaV1:
    """V1 简化: role.yaml 字段验证"""

    @pytest.fixture(scope='class')
    def role_schema(self):
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_role_yaml_excludes_is_super_admin(self, role_schema):
        """is_super_admin 字段已从 role.yaml 删除"""
        field_ids = [f['id'] for f in role_schema.get('fields', [])]
        assert 'is_super_admin' not in field_ids, \
            "is_super_admin 字段不应再存在于 role.yaml"

    def test_role_yaml_excludes_priority(self, role_schema):
        """priority 字段已从 role.yaml 删除"""
        field_ids = [f['id'] for f in role_schema.get('fields', [])]
        assert 'priority' not in field_ids, \
            "priority 字段不应再存在于 role.yaml"

    def test_role_yaml_has_core_fields(self, role_schema):
        """核心字段保留"""
        field_ids = [f['id'] for f in role_schema.get('fields', [])]
        for required in ['id', 'code', 'name', 'description', 'is_active', 'is_system', 'created_at']:
            assert required in field_ids, f"核心字段 {required} 不应被删除"


class TestRoleColumnsInDB:
    """V1 简化: DB 字段验证 (依赖 test conftest 的 DB 初始化)"""

    def test_roles_table_no_is_super_admin_column(self):
        """DB roles 表不应再含 is_super_admin 列"""
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', database=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        ))
        cursor = ds.execute("PRAGMA table_info(roles)")
        cols = [row[1] if not isinstance(row, dict) else row['name']
                for row in cursor.fetchall()]
        assert 'is_super_admin' not in cols, \
            "DB roles 表不应再含 is_super_admin 列"

    def test_roles_table_no_priority_column(self):
        """DB roles 表不应再含 priority 列"""
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', database=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        ))
        cursor = ds.execute("PRAGMA table_info(roles)")
        cols = [row[1] if not isinstance(row, dict) else row['name']
                for row in cursor.fetchall()]
        assert 'priority' not in cols, \
            "DB roles 表不应再含 priority 列"

    def test_admin_user_has_wildcard_permission(self):
        """Admin user 应通过角色获得 '*' 权限"""
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', database=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        ))
        cursor = ds.execute("""
            SELECT COUNT(DISTINCT u.id) AS c
            FROM users u
            JOIN user_group_members ugm ON u.id = ugm.user_id
            JOIN group_roles gr ON ugm.group_id = gr.group_id
            JOIN role_permissions rp ON gr.role_id = rp.role_id
            JOIN permissions p ON rp.permission_id = p.id
            WHERE p.code = '*' AND u.username = 'admin'
        """)
        row = cursor.fetchone()
        count = row[0] if not isinstance(row, dict) else row['c']
        assert count >= 1, "admin user 应通过 admin 角色获得 '*' 权限"


class TestRoleApiV1:
    """V1 简化: role API 响应不再含 is_super_admin / priority"""

    def test_list_roles_api_excludes_is_super_admin(self, api_client, admin_token):
        """GET /api/v1/roles 响应不再含 is_super_admin 字段"""
        resp = api_client.get(
            '/api/v1/roles',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data[:200]}"
        data = resp.get_json()
        assert data.get('success') is True
        items = self._extract_role_list(data)
        if items:
            for item in items:
                assert 'is_super_admin' not in item, \
                    f"role 列表响应不应含 is_super_admin: {item}"

    def test_list_roles_api_excludes_priority(self, api_client, admin_token):
        """GET /api/v1/roles 响应不再含 priority 字段"""
        resp = api_client.get(
            '/api/v1/roles',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        items = self._extract_role_list(data)
        if items:
            for item in items:
                assert 'priority' not in item, \
                    f"role 列表响应不应含 priority: {item}"

    @staticmethod
    def _extract_role_list(payload):
        """兼容 2 种 list 返回结构:
        - v1 直接 list: payload = {'success': True, 'data': [ {...}, ... ]}
        - v2 分页:      payload = {'success': True, 'data': {'items': [...], 'total': N}}
        """
        body = payload.get('data')
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return body.get('items') or []
        return []
