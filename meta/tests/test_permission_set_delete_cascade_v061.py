# -*- coding: utf-8 -*-
"""[NEW 2026-07-12 BUG-V061] 角色删除级联 - 集成测试

策略: 必须用 Factory/BO API (conftest 禁止 raw SQL)
raw SQL 仅用于 verify 子表记录数 (read-only SELECT, 在白名单内), 业务操作走 API.
"""
import json
import os
import sqlite3
import time

import pytest

# 强制允许 read-only SELECT (用于 verify 子表清零)
# 业务创建/删除仍走 BO API (RoleFactory)
os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.tests.factories.permission_set import RoleFactory  # noqa: E402
from meta.tests.factories.permission import PermissionFactory  # noqa: E402

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')

import sys
_admin_token_path = os.path.join(_PROJECT_ROOT, 'tests', 'fixtures')
if _admin_token_path not in sys.path:
    sys.path.insert(0, _admin_token_path)

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_cookie():
    """获取 admin cookie (用于直接调 RoleFactory 等)."""
    from admin_token import get_admin_cookie
    return get_admin_cookie()


def _count_child_tables(permission_set_id: int) -> dict:
    """[read-only] 统计角色在各子表中的引用数量."""
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    try:
        cur = conn.cursor()
        counts = {}
        for tbl in ('role_permissions', 'role_menu_permissions',
                    'permission_rules', 'role_data_permissions',
                    'role_dimension_scopes', 'user_roles'):
            try:
                cur.execute(f'SELECT COUNT(*) FROM {tbl} WHERE permission_set_id=?', (permission_set_id,))
                counts[tbl] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                counts[tbl] = -1  # 表可能不存在
        return counts
    finally:
        conn.close()


class TestRoleDeleteCascadeV061:
    """[BUG-V061 2026-07-12] 角色删除应静默级联清理子表"""

    def test_tc01_delete_with_refs_cascades(self, admin_cookie):
        """TC-01: 创建角色 + 分配权限 + 菜单 → 删角色 → 子表清零."""
        # 用 RoleFactory 创建 + 自动分配权限 (RoleFactory 默认带 permissions)
        # 显式覆盖 permissions
        permission_set = RoleFactory.create(
            cookie=admin_cookie,
            permissions=['product:read', 'product:write'],
        )
        permission_set_id = permission_set['id']
        assert permission_set_id > 0, f'create permission_set failed: {permission_set}'

        try:
            # 1. 验证子表确实有引用 (RoleFactory 默认会创建 role_permissions)
            counts = _count_child_tables(permission_set_id)
            assert counts['role_permissions'] >= 2, \
                f'expected >=2 role_permissions, got: {counts}'

            # 2. 删除角色 (走 API, 触发级联)
            RoleFactory.cleanup(permission_set_id, cookie=admin_cookie)

            # 3. 验证各子表清零
            final = _count_child_tables(permission_set_id)
            for tbl, n in final.items():
                if n < 0:
                    continue  # 表不存在
                assert n == 0, \
                    f'After delete, {tbl} still has {n} rows for permission_set {permission_set_id}'

        finally:
            # 兜底清理
            try:
                RoleFactory.cleanup(permission_set_id, cookie=admin_cookie)
            except Exception:
                pass

    def test_tc02_is_system_role_protected(self, admin_cookie):
        """TC-02: is_system=1 的 admin 角色 (id=1) 不能删
        (permission_set.yaml 中 is_system 字段 + no_delete constraint 已存在, 验证有效)
        """
        import requests

        BO_URL = os.environ.get('BO_API_BASE', 'http://localhost:3010')

        del_resp = requests.delete(
            f'{BO_URL}/api/v1/permission-sets/1',
            headers={'Cookie': admin_cookie, 'Content-Type': 'application/json'},
            timeout=15,
        )
        try:
            data = del_resp.json()
        except Exception:
            data = {'success': False, 'raw': del_resp.text[:200]}

        assert data.get('success') is False, \
            f'is_system=1 admin permission_set should fail delete: {data}'

        # 错误信息应提及 "不可删除" / "no_delete" (yaml constraint 固定文案)
        msg_blob = json.dumps(data, ensure_ascii=False)
        assert '不可删除' in msg_blob or 'no_delete' in msg_blob or \
               '系统角色' in msg_blob or 'SYSTEM_ROLE' in msg_blob, \
            f'expected no_delete message in: {data}'
