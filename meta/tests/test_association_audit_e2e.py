import pytest

pytestmark = pytest.mark.e2e

# -*- coding: utf-8 -*-
"""
关联操作审计日志 E2E 集成测试

测试完整 API 调用链路中关联操作的审计日志生成：
1. 用户组添加/移除成员 -> ASSOCIATE/DISSOCIATE 审计日志
2. 角色分配/移除 -> ASSOCIATE/DISSOCIATE 审计日志
3. Action 命名统一验证
"""

import pytest
import os
import sys
import sqlite3

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ.setdefault('TESTING', 'true')
from meta.services import async_audit_writer as _aaw
_aaw._TESTING_MODE = True

from meta.core.datasource import get_data_source


@pytest.fixture
def ds():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    return get_data_source("sqlite", database=db_path)


def _get_audit_logs(action=None, object_type=None, limit=50):
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    if action:
        sql += " AND action = ?"
        params.append(action)
    if object_type:
        sql += " AND object_type = ?"
        params.append(object_type)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def _create_user_group_with_roles(ds, user_id, role_id):
    """创建用户组并将用户添加到组，然后给组分配角色"""
    import time
    import random
    # v3.18: 添加随机后缀确保 code 唯一
    random_suffix = f'{int(time.time() * 1000) % 100000}_{random.randint(1000, 9999)}'
    group_code = f'audit_group_{user_id}_{random_suffix}'
    
    # v3.18: 确保 role 存在
    role_exists = ds.execute("SELECT 1 FROM roles WHERE id = ?", [role_id]).fetchone()
    if not role_exists:
        ds.execute("INSERT INTO roles (id, name, code) VALUES (?, ?, ?)",
            (role_id, f'AutoRole_{role_id}', f'auto_role_{role_id}'))
        ds.commit()
    
    # 先清理旧的用户组，避免残留数据
    ds.execute("DELETE FROM group_roles WHERE group_id IN (SELECT id FROM user_groups WHERE code LIKE ?)",
        (f'audit_group_{user_id}_%',))
    ds.execute("DELETE FROM user_group_members WHERE group_id IN (SELECT id FROM user_groups WHERE code LIKE ?)",
        (f'audit_group_{user_id}_%',))
    ds.execute("DELETE FROM user_groups WHERE code LIKE ?",
        (f'audit_group_{user_id}_%',))
    ds.commit()
    
    ds.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)",
        (group_code, f'Audit Group {user_id}'))
    ds.commit()  # 确保 group_id 可用
    
    # v3.18: 使用 SELECT MAX 获取 group_id，避免 last_insert_rowid() 问题
    group_id = ds.execute("SELECT MAX(id) FROM user_groups WHERE code = ?", [group_code]).fetchone()[0]
    
    if group_id is None:
        raise RuntimeError(f"Failed to create user_group with code: {group_code}")
    
    ds.execute("INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)",
        (user_id, group_id))
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)",
        (group_id, role_id))
    ds.commit()
    return group_id


def _cleanup_user_group_association(ds, group_id, role_id):
    """清理用户组-角色关联"""
    ds.execute("DELETE FROM group_roles WHERE group_id = ? AND role_id = ?",
        (group_id, role_id))
    ds.execute("DELETE FROM user_group_members WHERE group_id = ?", [group_id])
    ds.execute("DELETE FROM user_groups WHERE id = ?", [group_id])
    ds.commit()


class TestUserGroupAssociateAudit:
    """用户组关联操作审计日志测试"""

    def test_add_member_generates_associate_log(self, ds):
        user_id = 2
        group_id = 1

        ds.execute(
            "INSERT OR IGNORE INTO user_group_members (user_id, group_id) VALUES (?, ?)",
            [user_id, group_id]
        )
        ds.commit()

        from meta.services.audit_interceptor import AuditInterceptor as SvcAuditInterceptor
        auditor = SvcAuditInterceptor(ds)
        auditor.log_associate(
            object_type='user_group',
            object_id=str(group_id),
            tgt_type='user',
            tgt_id=str(user_id),
            association_name='members',
            user_id='1',
            user_name='admin',
        )

        ds.execute("DELETE FROM user_group_members WHERE user_id = ? AND group_id = ?",
                    [user_id, group_id])
        ds.commit()


class TestRoleAssignAudit:
    """角色分配审计日志测试"""

    def test_assign_role_generates_associate_log(self, ds):
        from meta.services.audit_interceptor import AuditInterceptor as SvcAuditInterceptor
        auditor = SvcAuditInterceptor(ds)

        # v3.18: 动态获取有效的 user_id 和 role_id
        user_row = ds.execute("SELECT id FROM users WHERE id > 1 LIMIT 1").fetchone()
        role_row = ds.execute("SELECT id FROM roles LIMIT 1").fetchone()
        if not user_row or not role_row:
            pytest.skip("需要有效的 user 和 role 数据")
        user_id = user_row[0]
        role_id = role_row[0]

        group_id = _create_user_group_with_roles(ds, user_id, role_id)

        auditor.log_associate(
            object_type='user_group',
            object_id=str(group_id),
            tgt_type='role',
            tgt_id=str(role_id),
            association_name='roles',
            user_id='1',
            user_name='admin',
        )

        _cleanup_user_group_association(ds, group_id, role_id)


class TestAssociateDissociateActionNaming:
    """验证 ASSOCIATE/DISSOCIATE 命名统一"""

    def test_associate_action_in_audit_logs(self, ds):
        from meta.services.audit_interceptor import AuditInterceptor as SvcAuditInterceptor
        auditor = SvcAuditInterceptor(ds)

        # v3.18: 动态获取有效的 user_id 和 role_id
        user_row = ds.execute("SELECT id FROM users WHERE id > 1 LIMIT 1").fetchone()
        role_row = ds.execute("SELECT id FROM roles LIMIT 1").fetchone()
        if not user_row or not role_row:
            pytest.skip("需要有效的 user 和 role 数据")
        user_id = user_row[0]
        role_id = role_row[0]

        group_id = _create_user_group_with_roles(ds, user_id, role_id)

        auditor.log_associate(
            object_type='user_group', object_id=str(group_id),
            tgt_type='role', tgt_id=str(role_id),
            association_name='roles',
            user_id='1', user_name='admin',
        )

        _cleanup_user_group_association(ds, group_id, role_id)

    def test_dissociate_action_in_audit_logs(self, ds):
        from meta.services.audit_interceptor import AuditInterceptor as SvcAuditInterceptor
        auditor = SvcAuditInterceptor(ds)

        # v3.18: 动态获取有效的 user_id 和 role_id
        user_row = ds.execute("SELECT id FROM users WHERE id > 1 LIMIT 1").fetchone()
        role_row = ds.execute("SELECT id FROM roles LIMIT 1").fetchone()
        if not user_row or not role_row:
            pytest.skip("需要有效的 user 和 role 数据")
        user_id = user_row[0]
        role_id = role_row[0]

        group_id = _create_user_group_with_roles(ds, user_id, role_id)

        _cleanup_user_group_association(ds, group_id, role_id)

        auditor.log_dissociate(
            object_type='user_group', object_id=str(group_id),
            tgt_type='role', tgt_id=str(role_id),
            association_name='roles',
            user_id='1', user_name='admin',
        )

    def test_no_new_assign_or_revoke_records(self, ds):
        from meta.services.audit_interceptor import AuditInterceptor as SvcAuditInterceptor
        auditor = SvcAuditInterceptor(ds)

        # v3.18: 动态获取有效的 user_id 和 role_id
        user_row = ds.execute("SELECT id FROM users WHERE id > 1 LIMIT 1").fetchone()
        role_row = ds.execute("SELECT id FROM roles LIMIT 1").fetchone()
        if not user_row or not role_row:
            pytest.skip("需要有效的 user 和 role 数据")
        user_id = user_row[0]
        role_id = role_row[0]

        group_id = _create_user_group_with_roles(ds, user_id, role_id)

        before_assign = len(_get_audit_logs( action='ASSIGN'))
        before_revoke = len(_get_audit_logs( action='REVOKE'))

        auditor.log_associate(
            object_type='user_group', object_id=str(group_id),
            tgt_type='role', tgt_id=str(role_id),
            association_name='roles',
            user_id='1', user_name='admin',
        )

        after_assign = len(_get_audit_logs( action='ASSIGN'))
        after_revoke = len(_get_audit_logs( action='REVOKE'))

        assert after_assign == before_assign, "No new ASSIGN records should be created"
        assert after_revoke == before_revoke, "No new REVOKE records should be created"

        _cleanup_user_group_association(ds, group_id, role_id)


class TestAuditLogActionCompleteness:
    """审计日志 action 完整性测试"""

    def test_expected_actions_present(self, ds):
        from meta.services.audit_interceptor import AuditInterceptor as SvcAuditInterceptor
        auditor = SvcAuditInterceptor(ds)

        # v3.18: 动态获取有效的 user_id 和 role_id
        user_row = ds.execute("SELECT id FROM users WHERE id > 1 LIMIT 1").fetchone()
        role_row = ds.execute("SELECT id FROM roles LIMIT 1").fetchone()
        if not user_row or not role_row:
            pytest.skip("需要有效的 user 和 role 数据")
        user_id = user_row[0]
        role_id = role_row[0]

        group_id = _create_user_group_with_roles(ds, user_id, role_id)

        auditor.log_associate(
            object_type='user_group', object_id=str(group_id),
            tgt_type='role', tgt_id=str(role_id),
            association_name='roles',
            user_id='1', user_name='admin',
        )

        auditor.log_dissociate(
            object_type='user_group', object_id=str(group_id),
            tgt_type='role', tgt_id=str(role_id),
            association_name='roles',
            user_id='1', user_name='admin',
        )

        _cleanup_user_group_association(ds, group_id, role_id)
