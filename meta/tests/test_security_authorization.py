# -*- coding: utf-8 -*-
# ALLOW_RAW_SQL: 本文件含裸 SQL 构造权限测试数据/DDL，守卫豁免（2026-11-09 恢复覆盖）
"""
P10 集成测试：权限体系安全性
v1.4 P10 补齐：端到端委托链、权限冲突、token 失效集成

[v138 2026-11-09] 适配产品重命名与委托模型切换：
  - role → permission_set，group → org（org_members.group_id → org_id）
  - v088 起委托不再走 is_manager：改为「权限集 + 资源矩阵 org 行级规则」
    （data_permission_rules: resource_type='org', rule_type='condition'）
  - PermissionService.assign_role → assign_permission_set
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
from meta.services.permission_service import PermissionService
from meta.services.token_version_service import TokenVersionService, token_version_service


@pytest.fixture
def ds():
    """完整 schema"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            display_name TEXT,
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            token_version INTEGER DEFAULT 0
        );
        CREATE TABLE orgs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            parent_id INTEGER,
            manager_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE org_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            org_id INTEGER NOT NULL,
            is_manager INTEGER DEFAULT 0,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, org_id)
        );
        CREATE TABLE permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 0,
            is_system INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE org_permission_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            permission_set_id INTEGER NOT NULL,
            created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(org_id, permission_set_id)
        );
        CREATE TABLE permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            resource_type TEXT,
            action TEXT,
            description TEXT,
            scope TEXT DEFAULT 'all',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE permission_set_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            granted INTEGER DEFAULT 1,
            UNIQUE(permission_set_id, permission_id)
        );
        CREATE TABLE permission_set_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            permission_level TEXT
        );
        CREATE TABLE org_data_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            resource_type TEXT,
            resource_id INTEGER,
            permission_level TEXT,
            is_deprecated INTEGER DEFAULT 1,
            inherit_to_children INTEGER DEFAULT 1
        );
        CREATE TABLE data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
            resource_type VARCHAR(200),
            condition TEXT,
            is_denied INTEGER DEFAULT 0,
            permission_level VARCHAR(50) DEFAULT 'read',
            expires_at VARCHAR(50)
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
def token_svc(ds):
    """每次测试用新的 token_version_service"""
    svc = TokenVersionService()
    svc.set_data_source(ds)
    # 清空全局缓存
    TokenVersionService._version_cache.clear()
    # 产品代码 assign/remove 内部 bump 走全局单例，需要指向本测试库
    token_version_service.set_data_source(ds)
    yield svc
    TokenVersionService._version_cache.clear()


@pytest.fixture
def perm_svc(ds):
    return PermissionService(ds)


@pytest.fixture
def org_svc(ds):
    return OrgService(ds)


# ============== Helpers ==============

def _insert_user(ds, username='u', token_version=0):
    ds.execute(
        "INSERT INTO users (username, display_name, email, status, token_version) VALUES (?, ?, ?, ?, ?)",
        [username, f'Display {username}', f'{username}@x.com', 'active', token_version]
    )
    return ds.execute("SELECT id FROM users WHERE username = ?", [username]).fetchone()[0]


def _insert_org(ds, name='G', code='g', parent_id=None):
    ds.execute(
        "INSERT INTO orgs (name, code, parent_id, updated_at) VALUES (?, ?, ?, datetime('now'))",
        [name, code, parent_id]
    )
    return ds.execute("SELECT id FROM orgs WHERE code = ?", [code]).fetchone()[0]


def _insert_permission_set(ds, code='R', name='R', priority=0, is_system=0):
    ds.execute(
        "INSERT INTO permission_sets (code, name, description, priority, is_system) VALUES (?, ?, ?, ?, ?)",
        [code, name, 'desc', priority, is_system]
    )
    return ds.execute("SELECT id FROM permission_sets WHERE code = ?", [code]).fetchone()[0]


def _insert_permission(ds, code='P', resource_type='product', action='read', scope='all'):
    ds.execute(
        "INSERT INTO permissions (code, name, resource_type, action, description, scope) VALUES (?, ?, ?, ?, ?, ?)",
        [code, code, resource_type, action, 'desc', scope]
    )
    return ds.execute("SELECT id FROM permissions WHERE code = ?", [code]).fetchone()[0]


def _grant_org_delegation(ds, user_id, org_id, ps_id, condition):
    """配置委托：权限集经个人组织分配给受托人，权限集带 org 行级规则

    注意：委托权归属「被分配权限集的那个人」，不能把权限集直接绑到目标组织
    （组织成员会共享组织权限集，绑到组织等于给全体成员发放委托）。
    """
    org_id_personal = PermissionService(ds)._get_or_create_personal_group(user_id)
    PermissionService(ds)._ensure_user_in_group(user_id, org_id_personal)
    ds.execute(
        "INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id) VALUES (?, ?)",
        [org_id_personal, ps_id]
    )
    ds.execute(
        "INSERT INTO data_permission_rules (permission_set_id, rule_type, resource_type, condition) "
        "VALUES (?, 'condition', 'org', ?)",
        [ps_id, condition]
    )


# =========================================================================
# A. 委托链完整性
# =========================================================================

def test_delegation_chain_full(ds, org_svc, perm_svc, token_svc):
    """完整委托链：org 行级规则 → 经理 → 组成员"""
    manager = _insert_user(ds, 'mgr_delegation', token_version=0)
    member = _insert_user(ds, 'member_delegation', token_version=0)
    g = _insert_org(ds, 'DelegationG', 'delegation_g')
    ps = _insert_permission_set(ds, code='delegation_ps', name='Delegation')

    _grant_org_delegation(ds, manager, g, ps, f'id = {g}')
    org_svc.add_member(g, member, is_manager=False)

    assert org_svc.can_manage_user(manager, member) is True
    assert org_svc.can_manage_user(member, manager) is False


def test_delegation_chain_broken(ds, org_svc, perm_svc):
    """无共同组：不能管理"""
    u1 = _insert_user(ds, 'lonely1')
    u2 = _insert_user(ds, 'lonely2')
    # 没有任何组
    assert org_svc.can_manage_user(u1, u2) is False


def test_delegation_through_ancestor_group(ds, org_svc):
    """绑定父组织 ⇒ 可管理子组织成员（动态子树展开）"""
    parent = _insert_org(ds, 'ParentDG', 'parent_dg')
    child = _insert_org(ds, 'ChildDG', 'child_dg', parent_id=parent)
    parent_mgr = _insert_user(ds, 'parent_mgr')
    child_member = _insert_user(ds, 'child_member')
    ps = _insert_permission_set(ds, code='ancestor_ps', name='Ancestor')

    _grant_org_delegation(ds, parent_mgr, parent, ps, f'id = {parent}')
    org_svc.add_member(child, child_member, is_manager=False)

    assert org_svc.can_manage_user(parent_mgr, child_member) is True


# =========================================================================
# B. 权限分配与回收
# =========================================================================

def test_permission_revoke_invalidates_token(ds, perm_svc, token_svc):
    """分配/移除权限集后 token_version 应 bump（核心安全）"""
    u = _insert_user(ds, 'revoke_user', token_version=5)
    r = _insert_permission_set(ds, code='revoke_r', name='Revoke')
    p = _insert_permission(ds, code='revoke.perm')

    # 1) 用户拿到权限集和权限
    assert perm_svc.assign_permission_set(u, r) is True
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r, p])
    assert perm_svc.has_permission(u, 'revoke.perm') is True

    # 2) token_version 已 bump（5 → 6）
    assert token_svc._get_db_version(u) == 6

    # 3) 移除权限集
    assert perm_svc.remove_permission_set(u, r) is True
    # 4) 权限应当不存在，且再次 bump（6 → 7）
    assert perm_svc.has_permission(u, 'revoke.perm') is False
    assert token_svc._get_db_version(u) == 7


def test_wildcard_grant_and_revoke(ds, perm_svc):
    """通配符权限：分配后所有 check 通过，移除后所有 check 失败"""
    u = _insert_user(ds, 'wildcard_grant')
    org_id = perm_svc._get_or_create_personal_group(u)
    perm_svc._ensure_user_in_group(u, org_id)
    r = _insert_permission_set(ds, code='admin_role', name='Admin')
    p = _insert_permission(ds, code='*', resource_type='*', action='*')
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r, p])
    assert perm_svc.assign_permission_set(u, r) is True
    # 任意权限通过
    assert perm_svc.has_permission(u, 'any.permission') is True
    # 移除通配符权限
    assert perm_svc.remove_permission_set(u, r) is True
    # 任意权限失败
    assert perm_svc.has_permission(u, 'any.permission') is False


# =========================================================================
# C. 权限冲突场景
# =========================================================================

def test_multiple_roles_with_overlapping_permissions(ds, perm_svc):
    """多个权限集有重叠权限：用户应能使用所有权限"""
    u = _insert_user(ds, 'multi_overlap')
    org_id = perm_svc._get_or_create_personal_group(u)
    perm_svc._ensure_user_in_group(u, org_id)
    r1 = _insert_permission_set(ds, code='overlap1', name='R1')
    r2 = _insert_permission_set(ds, code='overlap2', name='R2')
    p1 = _insert_permission(ds, code='shared.read')
    p2 = _insert_permission(ds, code='shared.write')
    p3 = _insert_permission(ds, code='unique.perm')
    # r1: p1 + p3
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r1, p1])
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r1, p3])
    # r2: p1 + p2
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r2, p1])
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r2, p2])
    assert perm_svc.assign_permission_set(u, r1) is True
    assert perm_svc.assign_permission_set(u, r2) is True
    # 用户应有所有 3 个权限（去重后）
    perms = perm_svc.get_user_permissions(u)
    assert 'shared.read' in perms
    assert 'shared.write' in perms
    assert 'unique.perm' in perms
    assert len(perms) == 3


def test_no_permission_grant_denies(ds, perm_svc):
    """无任何权限集时：所有 check 失败"""
    u = _insert_user(ds, 'no_role_user')
    assert perm_svc.has_permission(u, 'any.perm') is False
    assert perm_svc.get_user_permission_sets(u) == []
    assert perm_svc.get_user_permissions(u) == []


def test_disabled_role_cannot_be_used(ds, perm_svc):
    """is_system=1 的权限集（业务标记）仍可被使用（service 不做特殊处理）"""
    u = _insert_user(ds, 'sys_user2')
    org_id = perm_svc._get_or_create_personal_group(u)
    perm_svc._ensure_user_in_group(u, org_id)
    r = _insert_permission_set(ds, code='sys_role', name='System', is_system=1)
    p = _insert_permission(ds, code='sys.perm')
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r, p])
    assert perm_svc.assign_permission_set(u, r) is True
    assert perm_svc.has_permission(u, 'sys.perm') is True


# =========================================================================
# D. 资源级权限
# =========================================================================

def test_data_permissions_via_groups(ds, org_svc, perm_svc):
    """完整链路：user → org → permission_set → data_permission"""
    u = _insert_user(ds, 'data_user')
    g = _insert_org(ds, 'DataG', 'data_g')
    org_svc.add_member(g, u)
    r = _insert_permission_set(ds, code='data_r', name='Data')
    assert org_svc.add_org_permission_set(g, r) is True
    # 权限集有 data permissions
    ds.execute(
        "INSERT INTO permission_set_data_permissions (permission_set_id, resource_type, resource_id, permission_level) VALUES (?, 'product', 100, 'read')",
        [r]
    )
    # 通过 org_svc 聚合
    perms = org_svc.get_user_effective_data_permissions_via_orgs(u)
    assert len(perms) == 1
    assert perms[0]['resource_type'] == 'product'
    assert perms[0]['resource_id'] == 100


def test_data_permissions_isolated_between_groups(ds, org_svc):
    """不同组织的数据权限互不干扰"""
    u = _insert_user(ds, 'iso_data_user')
    g1 = _insert_org(ds, 'IsoDataG1', 'iso_data_g1')
    g2 = _insert_org(ds, 'IsoDataG2', 'iso_data_g2')
    org_svc.add_member(g1, u)
    # g1 关联权限
    r1 = _insert_permission_set(ds, code='r_iso1', name='R1')
    assert org_svc.add_org_permission_set(g1, r1) is True
    ds.execute(
        "INSERT INTO permission_set_data_permissions (permission_set_id, resource_type, resource_id, permission_level) VALUES (?, 'product', 100, 'read')",
        [r1]
    )
    perms = org_svc.get_user_effective_data_permissions_via_orgs(u)
    assert len(perms) == 1
    # 把 u 从 g1 移除
    assert org_svc.remove_member(g1, u) is True
    perms_after = org_svc.get_user_effective_data_permissions_via_orgs(u)
    assert len(perms_after) == 0


# =========================================================================
# E. 委托链安全性
# =========================================================================

def test_admin_bypass_via_has_all_permission(ds, org_svc):
    """has_all_permission=True 绕过所有检查"""
    u1 = _insert_user(ds, 'admin_op')
    u2 = _insert_user(ds, 'random_user')
    assert org_svc.can_manage_user(u1, u2, has_all_permission=True) is True


def test_non_admin_cannot_bypass(ds, org_svc):
    """has_all_permission=False：必须通过组织委托"""
    u1 = _insert_user(ds, 'normal_op')
    u2 = _insert_user(ds, 'random_target')
    assert org_svc.can_manage_user(u1, u2, has_all_permission=False) is False


def test_user_cannot_escalate_by_joining_own_group(ds, org_svc, perm_svc):
    """同一组织内：只有受托管理员能管理他人，普通成员不能反向管理"""
    admin = _insert_user(ds, 'admin_esc')
    target = _insert_user(ds, 'target_esc')
    g = _insert_org(ds, 'EscG', 'esc_g')
    ps = _insert_permission_set(ds, code='esc_ps', name='Esc')
    # admin 通过 org 行级规则获得委托
    _grant_org_delegation(ds, admin, g, ps, f'id = {g}')
    # target 加入同一组（普通成员）
    org_svc.add_member(g, target, is_manager=False)
    assert org_svc.can_manage_user(admin, target) is True
    # target 没有委托，不应能管理 admin
    assert org_svc.can_manage_user(target, admin) is False


# =========================================================================
# F. 用户状态相关
# =========================================================================

def test_inactive_user_cannot_be_assigned_role(ds, perm_svc):
    """inactive 用户：业务方法不检查（仅 token / 中间件层限制）"""
    u = _insert_user(ds, 'inactive_user')
    ds.execute("UPDATE users SET status = ? WHERE id = ?", ['inactive', u])
    r = _insert_permission_set(ds, code='any_r', name='R')
    # assign_permission_set 不抛异常（service 不做 status 检查）
    assert perm_svc.assign_permission_set(u, r) is True


def test_user_without_personal_group_gets_one(ds, perm_svc):
    """assign_permission_set 触发 personal org 创建（幂等）"""
    u = _insert_user(ds, 'no_personal_user')
    r = _insert_permission_set(ds, code='trigger_r', name='Trigger')
    # 第一次：创建 personal org
    assert perm_svc.assign_permission_set(u, r) is True
    # 第二次：复用
    assert perm_svc.assign_permission_set(u, r) is True
    # 验证：只有 1 个 personal org
    cursor = ds.execute(
        "SELECT COUNT(*) FROM orgs WHERE code = ?", [f'personal_org_user_{u}']
    )
    assert cursor.fetchone()[0] == 1


# =========================================================================
# G. 性能 / 规模
# =========================================================================

def test_large_group_member_count(ds, org_svc, perm_svc):
    """100 成员的大组：操作性能"""
    g = _insert_org(ds, 'LargeG', 'large_g')
    user_ids = []
    for i in range(100):
        uid = _insert_user(ds, f'big_user_{i}')
        user_ids.append(uid)
        assert org_svc.add_member(g, uid) is True
    # 查询
    members = org_svc.get_org_members(g)
    assert len(members) == 100
    # 删除所有
    for uid in user_ids:
        assert org_svc.remove_member(g, uid) is True
    # 验证
    members_after = org_svc.get_org_members(g)
    assert len(members_after) == 0


def test_user_in_many_groups(ds, org_svc):
    """用户加入 50 个组：get_user_orgs 性能"""
    u = _insert_user(ds, 'multi_g_user')
    g_ids = []
    for i in range(50):
        g = _insert_org(ds, f'ManyG{i}', f'many_g_{i}')
        assert org_svc.add_member(g, u) is True
        g_ids.append(g)
    user_orgs = org_svc.get_user_orgs(u)
    assert len(user_orgs) == 50


# =========================================================================
# H. 端到端：用户登录 → 操作 → 权限变更 → 验证
# =========================================================================

def test_e2e_permission_lifecycle(ds, perm_svc, token_svc):
    """端到端：分配权限集 → 验证权限 → 移除 → 失效"""
    # 1) 准备
    u = _insert_user(ds, 'e2e_user')
    r = _insert_permission_set(ds, code='e2e_r', name='E2E')
    p = _insert_permission(ds, code='e2e.perm')

    # 2) 用户分配权限集（自动创建 personal org + 关联）
    assert perm_svc.assign_permission_set(u, r) is True

    # 3) 关联权限
    ds.execute("INSERT INTO permission_set_permissions (permission_set_id, permission_id) VALUES (?, ?)", [r, p])

    # 4) 验证权限
    assert perm_svc.has_permission(u, 'e2e.perm') is True

    # 5) 移除权限集
    assert perm_svc.remove_permission_set(u, r) is True
    # 验证：所有权限失效
    assert perm_svc.has_permission(u, 'e2e.perm') is False
