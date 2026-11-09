# -*- coding: utf-8 -*-
# ALLOW_RAW_SQL: 本文件含裸 SQL 构造组织测试数据/DDL，守卫豁免（2026-11-09 恢复覆盖）
"""
P9 单元测试：OrgService 业务方法
[v089] UserGroupService 已 Sunset，本文件统一改用 OrgService（group → org 重命名）
[v088] add_member(is_manager=True) 已废弃：委托改由「权限集 + 资源矩阵 org 行级规则」实现
"""
import pytest

pytestmark = pytest.mark.integration

import sys
import os
import sqlite3
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.org_service import OrgService


@pytest.fixture
def ds():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orgs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            parent_id INTEGER,
            manager_id INTEGER,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS org_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            org_id INTEGER NOT NULL,
            is_manager INTEGER DEFAULT 0,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, org_id)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            display_name TEXT,
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 0,
            is_system INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS org_permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            permission_set_id INTEGER NOT NULL,
            created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(org_id, permission_set_id)
        );
        CREATE TABLE IF NOT EXISTS org_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            permission_level TEXT,
            is_deprecated INTEGER DEFAULT 1,
            inherit_to_children INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS permission_set_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            permission_level TEXT,
            inherit_to_children INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            rule_type TEXT DEFAULT 'condition',
            resource_type TEXT,
            condition TEXT,
            is_denied INTEGER DEFAULT 0,
            permission_level TEXT DEFAULT 'read'
        );
    """)
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

        def commit(self):
            self._conn.commit()

    yield MockDS(conn)
    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def svc(ds):
    return OrgService(ds)


# ============== Helpers ==============

def _insert_user(ds, username='testuser', display_name='Test User'):
    ds.execute(
        "INSERT INTO users (username, display_name, email, status) VALUES (?, ?, ?, ?)",
        [username, display_name, f'{username}@test.com', 'active']
    )
    cursor = ds.execute("SELECT id FROM users WHERE username = ?", [username])
    return cursor.fetchone()[0]


def _insert_org(ds, name='TestGroup', code='test_group', parent_id=None, manager_id=None):
    ds.execute(
        "INSERT INTO orgs (name, code, parent_id, manager_id) VALUES (?, ?, ?, ?)",
        [name, code, parent_id, manager_id]
    )
    cursor = ds.execute("SELECT id FROM orgs WHERE code = ?", [code])
    return cursor.fetchone()[0]


def _insert_ps(ds, name='TestRole', code='test_role'):
    ds.execute(
        "INSERT INTO permission_sets (code, name, description, priority, is_system) VALUES (?, ?, ?, ?, ?)",
        [code, name, 'desc', 0, 0]
    )
    cursor = ds.execute("SELECT id FROM permission_sets WHERE code = ?", [code])
    return cursor.fetchone()[0]


def _grant_delegation(ds, user_id, org_id, ps_id, condition):
    """委托 = 权限集分配给用户个人组织 + org 行级规则（v088 起唯一合法路径）"""
    from meta.services.permission_service import PermissionService
    personal = PermissionService(ds)._get_or_create_personal_group(user_id)
    PermissionService(ds)._ensure_user_in_group(user_id, personal)
    ds.execute(
        "INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id) VALUES (?, ?)",
        [personal, ps_id]
    )
    ds.execute(
        "INSERT INTO data_permission_rules (permission_set_id, rule_type, resource_type, condition) "
        "VALUES (?, 'condition', 'org', ?)",
        [ps_id, condition]
    )


# ============== 1. get_org_by_code (唯一主表方法) ==============

def test_get_org_by_code(svc, ds):
    """P8 保留: 根据 code 获取组织"""
    _insert_org(ds, 'GroupY', 'grp_y')
    result = svc.get_org_by_code('grp_y')
    assert result is not None
    assert result['name'] == 'GroupY'


def test_get_org_by_code_not_found(svc, ds):
    """不存在的 code 返回 None"""
    result = svc.get_org_by_code('nonexistent')
    assert result is None


# ============== 2. 成员管理 ==============

def test_add_member_and_get_org_members(svc, ds):
    """添加成员 + 获取成员列表（v088 起 is_manager 恒为 0）"""
    gid = _insert_org(ds, 'MemberGroup', 'mem_grp')
    uid = _insert_user(ds, 'member1')
    assert svc.add_member(gid, uid) is True
    members = svc.get_org_members(gid)
    assert len(members) == 1
    assert members[0]['user_id'] == uid
    assert members[0]['is_manager'] == 0


def test_add_member_rejects_is_manager(ds):
    """v088 废弃契约：is_manager=True 一律拒绝"""
    gid = _insert_org(ds, 'DeprecatedGroup', 'deprecated_grp')
    uid = _insert_user(ds, 'deprecated_user')
    assert svc_add_member(ds, gid, uid) is False
    assert OrgService(ds).is_member(gid, uid) is False


def svc_add_member(ds, gid, uid):
    return OrgService(ds).add_member(gid, uid, is_manager=True)


def test_remove_member(svc, ds):
    """移除成员"""
    gid = _insert_org(ds, 'RmGroup', 'rm_grp')
    uid = _insert_user(ds, 'rm_user')
    svc.add_member(gid, uid)
    result = svc.remove_member(gid, uid)
    assert result is True
    assert not svc.is_member(gid, uid)


def test_is_member(svc, ds):
    """检查成员关系"""
    gid = _insert_org(ds, 'CheckGroup', 'chk_grp')
    uid = _insert_user(ds, 'chk_user')
    assert svc.is_member(gid, uid) is False
    svc.add_member(gid, uid)
    assert svc.is_member(gid, uid) is True


def test_get_user_orgs(svc, ds):
    """获取用户所属的所有组织"""
    gid1 = _insert_org(ds, 'G1', 'g1')
    gid2 = _insert_org(ds, 'G2', 'g2')
    uid = _insert_user(ds, 'user_in_groups')
    svc.add_member(gid1, uid)
    svc.add_member(gid2, uid)
    groups = svc.get_user_orgs(uid)
    assert len(groups) == 2
    group_ids = [g['id'] for g in groups]
    assert gid1 in group_ids
    assert gid2 in group_ids
    # v088 起 is_manager 恒为 0
    assert all(g['is_manager'] == 0 for g in groups)


def test_is_org_manager_deprecated_flag(svc, ds):
    """v088 起 is_manager 恒为 0 → is_org_manager 恒 False"""
    gid = _insert_org(ds, 'MgrGroup', 'mgr_grp')
    uid = _insert_user(ds, 'mgr_user')
    assert svc.is_org_manager(gid, uid) is False
    svc.add_member(gid, uid)
    assert svc.is_org_manager(gid, uid) is False


# ============== 3. 层级查询 ==============

def test_get_child_orgs(svc, ds):
    """获取单层子组织"""
    root = _insert_org(ds, 'Root', 'root')
    _insert_org(ds, 'C1', 'c1', parent_id=root)
    _insert_org(ds, 'C2', 'c2', parent_id=root)
    children = svc.get_child_orgs(root)
    codes = [c['code'] for c in children]
    assert 'c1' in codes
    assert 'c2' in codes
    assert len(children) == 2


def test_get_all_descendant_orgs(svc, ds):
    """递归获取所有子孙组织 ID"""
    root = _insert_org(ds, 'Root', 'root')
    c1 = _insert_org(ds, 'C1', 'c1', parent_id=root)
    c2 = _insert_org(ds, 'C2', 'c2', parent_id=root)
    gc1 = _insert_org(ds, 'GC1', 'gc1', parent_id=c1)
    gc2 = _insert_org(ds, 'GC2', 'gc2', parent_id=c2)
    descendants = svc.get_all_descendant_orgs(root)
    assert set(descendants) == {c1, c2, gc1, gc2}


def test_get_all_ancestor_orgs(svc, ds):
    """递归获取所有祖先组织 ID"""
    root = _insert_org(ds, 'Root', 'root')
    p = _insert_org(ds, 'P', 'p', parent_id=root)
    gc = _insert_org(ds, 'GC', 'gc', parent_id=p)
    ancestors = svc.get_all_ancestor_orgs(gc)
    assert p in ancestors
    assert root in ancestors
    assert gc not in ancestors


def test_get_org_tree(svc, ds):
    """构建嵌套树结构"""
    root = _insert_org(ds, 'Root', 'root')
    _insert_org(ds, 'C1', 'c1', parent_id=root)
    _insert_org(ds, 'C2', 'c2', parent_id=root)
    tree = svc.get_org_tree()
    assert len(tree) >= 1
    root_node = next(n for n in tree if n['code'] == 'root')
    assert len(root_node['children']) == 2


# ============== 4. 委托授权（v088 新模型） ==============

def test_get_managed_orgs(svc, ds):
    """受托人管理的组织列表来自资源矩阵 org 行级规则"""
    gid = _insert_org(ds, 'ManagedGroup', 'mgd_grp')
    uid = _insert_user(ds, 'manager1')
    ps = _insert_ps(ds, 'Delegate', 'delegate_ps')
    _grant_delegation(ds, uid, gid, ps, f'id = {gid}')
    managed = svc.get_managed_orgs(uid)
    assert gid in managed


def test_can_manage_user_with_all_permission(svc, ds):
    """has_all_permission=True 直接返回 True"""
    assert svc.can_manage_user(1, 2, has_all_permission=True) is True


def test_can_manage_user_shared_org(svc, ds):
    """受托管理员可管理同组织成员"""
    gid = _insert_org(ds, 'SharedGroup', 'shared_grp')
    op = _insert_user(ds, 'operator')
    target = _insert_user(ds, 'target')
    ps = _insert_ps(ds, 'SharedDelegate', 'shared_delegate')
    _grant_delegation(ds, op, gid, ps, f'id = {gid}')
    svc.add_member(gid, target)
    assert svc.can_manage_user(op, target) is True
    # 反向不可（target 没有委托权限集）
    assert svc.can_manage_user(target, op) is False


def test_can_manage_user_no_common_org(svc, ds):
    """无委托关系 → False"""
    gid = _insert_org(ds, 'GroupA', 'grp_a')
    op = _insert_user(ds, 'op2')
    target = _insert_user(ds, 'target2')
    svc.add_member(gid, op)  # op 在 A（只是普通成员）
    assert svc.can_manage_user(op, target) is False


def test_get_manageable_users(svc, ds):
    """受托管理员获取可管理用户列表"""
    gid = _insert_org(ds, 'ManageGroup', 'manage_grp')
    op = _insert_user(ds, 'op_user')
    other = _insert_user(ds, 'other_user')
    ps = _insert_ps(ds, 'ManageDelegate', 'manage_delegate')
    _grant_delegation(ds, op, gid, ps, f'id = {gid}')
    svc.add_member(gid, other)
    manageable = svc.get_manageable_users(op)
    assert other in manageable


# ============== 5. 权限集关联 ==============

def test_get_org_permission_sets(svc, ds):
    """获取组织关联的权限集"""
    gid = _insert_org(ds, 'RoleGroup', 'role_grp')
    rid = _insert_ps(ds, 'LinkedRole', 'linked_role')
    ds.execute(
        "INSERT INTO org_permission_sets (org_id, permission_set_id) VALUES (?, ?)",
        [gid, rid]
    )
    roles = svc.get_org_permission_sets(gid)
    assert len(roles) == 1
    assert roles[0]['permission_set_id'] == rid


def test_add_org_permission_set(svc, ds):
    """添加权限集到组织"""
    gid = _insert_org(ds, 'AddRoleGrp', 'add_role_grp')
    rid = _insert_ps(ds, 'AddedRole', 'added_role')
    result = svc.add_org_permission_set(gid, rid, created_by=1)
    assert result is True
    assert len(svc.get_org_permission_sets(gid)) == 1


def test_remove_org_permission_set(svc, ds):
    """从组织移除权限集"""
    gid = _insert_org(ds, 'RmRoleGrp', 'rm_role_grp')
    rid = _insert_ps(ds, 'RemovableRole', 'removable_role')
    svc.add_org_permission_set(gid, rid)
    result = svc.remove_org_permission_set(gid, rid)
    assert result is True
    assert len(svc.get_org_permission_sets(gid)) == 0


def test_set_org_permission_sets_replaces(svc, ds):
    """set_org_permission_sets 全量替换"""
    gid = _insert_org(ds, 'SetRoleGrp', 'set_role_grp')
    r1 = _insert_ps(ds, 'Role1', 'role_1')
    r2 = _insert_ps(ds, 'Role2', 'role_2')
    r3 = _insert_ps(ds, 'Role3', 'role_3')
    svc.add_org_permission_set(gid, r1)
    svc.add_org_permission_set(gid, r2)
    svc.set_org_permission_sets(gid, [r3])
    roles = svc.get_org_permission_sets(gid)
    role_ids = [r['permission_set_id'] for r in roles]
    assert role_ids == [r3]
    assert r1 not in role_ids
    assert r2 not in role_ids


def test_get_permission_sets_not_in_org(svc, ds):
    """获取未关联到组织的权限集"""
    gid = _insert_org(ds, 'ExclusiveGrp', 'exclusive_grp')
    r1 = _insert_ps(ds, 'Linked1', 'linked_1')
    r2 = _insert_ps(ds, 'Linked2', 'linked_2')
    r3 = _insert_ps(ds, 'NotLinked', 'not_linked')
    svc.add_org_permission_set(gid, r1)
    svc.add_org_permission_set(gid, r2)
    not_linked = svc.get_permission_sets_not_in_org(gid)
    not_linked_ids = [r['id'] for r in not_linked]
    assert r3 in not_linked_ids
    assert r1 not in not_linked_ids
    assert r2 not in not_linked_ids


# ============== 6. 权限链路聚合 ==============

def test_get_user_effective_data_permissions_via_orgs(svc, ds):
    """user → org → permission_set → data_permission 链路聚合"""
    uid = _insert_user(ds, 'perm_user')
    gid = _insert_org(ds, 'PermGroup', 'perm_grp')
    svc.add_member(gid, uid)
    rid = _insert_ps(ds, 'DataRole', 'data_role')
    svc.add_org_permission_set(gid, rid)
    ds.execute(
        "INSERT INTO permission_set_data_permissions (permission_set_id, resource_type, resource_id, permission_level) VALUES (?, ?, ?, ?)",
        [rid, 'product', 100, 'read']
    )
    perms = svc.get_user_effective_data_permissions_via_orgs(uid)
    assert len(perms) == 1
    assert perms[0]['resource_type'] == 'product'
    assert perms[0]['resource_id'] == 100
    assert perms[0]['permission_level'] == 'read'


def test_get_user_effective_data_permissions_via_orgs_no_perm(svc, ds):
    """无关联权限返回空列表"""
    uid = _insert_user(ds, 'no_perm_user')
    perms = svc.get_user_effective_data_permissions_via_orgs(uid)
    assert perms == []


# ============== 7. 迁移工具 ==============

def test_migrate_org_data_permissions_to_roles(svc, ds):
    """把旧的 org_data_permissions 迁移到权限集模型"""
    gid = _insert_org(ds, 'MigGroup', 'mig_grp')
    ds.execute(
        "INSERT INTO org_data_permissions (org_id, resource_type, resource_id, permission_level, is_deprecated) VALUES (?, ?, ?, ?, 1)",
        [gid, 'product', 200, 'write']
    )
    result = svc.migrate_org_data_permissions_to_roles()
    assert result is not None
    # 迁移后应有 migrated_<code> 权限集并关联到组织
    migrated = svc.get_org_permission_sets(gid)
    assert any(r['code'] == 'migrated_mig_grp' for r in migrated)


# ============== 8. _get_object 内部方法 ==============

def test_get_object_for_audit(svc, ds):
    """_get_object 用于审计日志兼容"""
    gid = _insert_org(ds, 'AuditGroup', 'audit_grp')
    obj = svc._get_object(gid)
    assert obj is not None
    assert obj['code'] == 'audit_grp'


def test_get_object_not_found(svc, ds):
    """不存在的 ID 返回 None"""
    obj = svc._get_object(9999)
    assert obj is None
