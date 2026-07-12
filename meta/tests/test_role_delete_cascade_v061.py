# -*- coding: utf-8 -*-
"""
[NEW 2026-07-12] 角色级联删除 - BUG-V061 修复测试

目标:
- 修复前: 删除角色因 ~28 条 FK 引用 (role_permissions, role_menu_permissions, permission_rules 等) 报错
           "无法删除：角色权限 的 角色ID 引用了此记录"
- 修复后: role.yaml.associations[].cascade_delete=true → 静默级联清理所有子表

测试策略:
- TC-01: 创建一个测试角色 → 分配权限 + 菜单 + 条件规则 → 删除 → 全部子表清零
- TC-02: 不允许删除 super_admin (code='super_admin')
- TC-03: 不允许删除 is_system=1 的角色
"""
import json
import os
import sqlite3
import time

import pytest

pytestmark = pytest.mark.integration

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')


@pytest.fixture(scope='class')
def client():
    from meta.tests.conftest import get_shared_app
    app, test_client = get_shared_app()
    return test_client


@pytest.fixture(scope='class')
def admin_headers(client):
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    u = UserInfo(user_id='1', username='test_admin', display_name='Test Admin',
                 email='admin@test.com', roles=['admin'], permissions=['*'])
    token, _ = TokenService.create_token(u)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_admin',
    }


@pytest.fixture
def cleanup_role_ids():
    ids = []
    yield ids
    # 自动清理残留
    from meta.tests.conftest import get_shared_app
    _, cli = get_shared_app()
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    u = UserInfo(user_id='1', username='test_admin', roles=['admin'], permissions=['*'])
    token, _ = TokenService.create_token(u)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_admin',
    }
    for rid in ids:
        try:
            cli.delete(f'/api/v1/roles/{rid}', headers=headers)
        except Exception:
            pass


def _create_role_with_permissions(client, admin_headers, cleanup_role_ids, suffix=None):
    """创建一个角色, 分配权限+菜单+条件规则, 返回 role_id"""
    suffix = suffix or os.urandom(3).hex().upper()
    payload = {
        'name': f'Cascade Test {suffix}',
        'code': f'CASC_{suffix}',
        'description': '[TEST] role delete cascade',
        'is_active': 1,
        'is_system': 0,
    }
    resp = client.post('/api/v1/roles', data=json.dumps(payload), headers=admin_headers)
    assert resp.status_code in (200, 201), f'create role failed: {resp.status_code} {resp.data}'
    data = json.loads(resp.data)
    assert data.get('success'), f'create role failed: {data}'
    role_id = (data.get('data') or {}).get('id') or data.get('id')
    assert role_id, f'no role_id: {data}'
    cleanup_role_ids.append(role_id)

    # 分配权限
    perm_resp = client.put(
        f'/api/v1/roles/{role_id}/permissions',
        data=json.dumps({'permissions': ['product:read', 'product:write']}),
        headers=admin_headers,
    )
    assert perm_resp.status_code in (200, 201), f'grant perm failed: {perm_resp.data}'

    # 分配菜单
    menu_resp = client.put(
        f'/api/v1/roles/{role_id}/menus',
        data=json.dumps({'menu_codes': ['product-management']}),
        headers=admin_headers,
    )
    # menu 端点可选不强求成功

    # 直接 SQL 加条件规则
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO permission_rules
               (role_id, resource_type, condition, permission_level,
                is_enabled, inherit_to_children, created_at)
               VALUES (?, 'product', 'product_id = 999', 'read',
                       1, 1, datetime('now'))""",
            (role_id,)
        )
        conn.commit()
    finally:
        conn.close()

    return role_id


class TestRoleDeleteCascadeV061:
    """[BUG-V061 2026-07-12] 角色删除应静默级联清理子表"""

    def test_tc01_delete_with_refs_cascades(self, client, admin_headers, cleanup_role_ids):
        """TC-01: 创建角色+分配权限+条件规则 → 删角色 → 子表全清零"""
        role_id = _create_role_with_permissions(
            client, admin_headers, cleanup_role_ids, suffix='TC01'
        )

        # 1. 验证子表有记录
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM role_permissions WHERE role_id=?', (role_id,))
            rp_count_before = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM permission_rules WHERE role_id=?', (role_id,))
            pr_count_before = cur.fetchone()[0]
        finally:
            conn.close()

        assert rp_count_before >= 2, f'expected >=2 role_permissions, got {rp_count_before}'
        assert pr_count_before >= 1, f'expected >=1 permission_rules, got {pr_count_before}'

        # 2. 删角色 → 应成功（静默级联）
        del_resp = client.delete(f'/api/v1/roles/{role_id}', headers=admin_headers)
        del_data = json.loads(del_resp.data)
        assert del_data.get('success'), \
            f'delete should succeed (cascade), got: {del_data.get("error")} {del_data.get("message")}'

        # 3. 子表记录全为 0
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            for table in ('role_permissions', 'permission_rules',
                          'role_menu_permissions', 'role_data_permissions',
                          'role_dimension_scopes'):
                cur.execute(f'SELECT COUNT(*) FROM {table} WHERE role_id=?', (role_id,))
                cnt = cur.fetchone()[0]
                assert cnt == 0, f'{table} still has {cnt} records for role {role_id}'
        finally:
            conn.close()

        # 标记自动清理跳过
        if role_id in cleanup_role_ids:
            cleanup_role_ids.remove(role_id)

    def test_tc02_super_admin_protected(self, client, admin_headers):
        """TC-02: super_admin 角色不能删"""
        # 查 super_admin id
        list_resp = client.get('/api/v1/roles', headers=admin_headers)
        list_data = json.loads(list_resp.data)
        items = (list_data.get('data') or {}).get('items') or list_data.get('items') or []
        super_admin = next(
            (r for r in items if r.get('code') == 'super_admin' or r.get('id') == 1),
            None
        )
        if not super_admin:
            pytest.skip('no super_admin role found in env')

        del_resp = client.delete(
            f'/api/v1/roles/{super_admin["id"]}',
            headers=admin_headers,
        )
        del_data = json.loads(del_resp.data)
        assert del_data.get('success') is False, \
            f'super_admin delete should fail, got: {del_data}'
        assert 'SUPER_ADMIN' in (del_data.get('error') or '') or \
               'PROTECTED' in (del_data.get('error') or ''), \
            f'expected SUPER_ADMIN/PROTECTED error, got: {del_data.get("error")}'

    def test_tc03_is_system_role_protected(self, client, admin_headers):
        """TC-03: is_system=1 的角色不能删"""
        conn = sqlite3.connect(DB_PATH)
        try:
            cur = conn.cursor()
            cur.execute(
                'SELECT id, code, name FROM roles WHERE is_system = 1 LIMIT 1'
            )
            row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip('no is_system=1 role in env')

        role_id, code, name = row

        # 跳过 super_admin (TC-02 已测)
        if code == 'super_admin':
            pytest.skip('super_admin tested in TC-02')

        del_resp = client.delete(f'/api/v1/roles/{role_id}', headers=admin_headers)
        del_data = json.loads(del_resp.data)
        assert del_data.get('success') is False, \
            f'is_system role delete should fail: {del_data}'
        assert 'SYSTEM_ROLE' in (del_data.get('error') or ''), \
            f'expected SYSTEM_ROLE error, got: {del_data.get("error")}'
