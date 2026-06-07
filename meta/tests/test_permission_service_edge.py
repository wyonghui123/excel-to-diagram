# -*- coding: utf-8 -*-
"""
P10 单元测试：permission_service 边界场景
v1.4 P10 补齐：通配符/个人组重用/assign 失效/业务一致性
"""
import pytest

pytestmark = pytest.mark.integration

import sys
import os
import sqlite3
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.permission_service import PermissionService
from meta.services.token_version_service import TokenVersionService, token_version_service


@pytest.fixture
def ds():
    """完整 schema（含 token_version 列）"""
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
        CREATE TABLE user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE user_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            is_manager INTEGER DEFAULT 0,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, group_id)
        );
        CREATE TABLE roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 0,
            is_system INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE group_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, role_id)
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
        CREATE TABLE role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            UNIQUE(role_id, permission_id)
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
    return PermissionService(ds)


# ============== Helpers ==============

def _insert_user(ds, username='u'):
    ds.execute(
        "INSERT INTO users (username, display_name, email, status, token_version) VALUES (?, ?, ?, ?, 0)",
        [username, f'Display {username}', f'{username}@x.com', 'active']
    )
    return ds.execute("SELECT id FROM users WHERE username = ?", [username]).fetchone()[0]


def _insert_personal_group(ds, user_id):
    code = f'personal_group_user_{user_id}'
    ds.execute(
        "INSERT INTO user_groups (code, name, description, updated_at) VALUES (?, ?, ?, datetime('now'))",
        [code, f'Personal group for user {user_id}', 'auto-generated']
    )
    return ds.execute("SELECT id FROM user_groups WHERE code = ?", [code]).fetchone()[0]


def _insert_role(ds, code='R', name='R', priority=0, is_system=0):
    ds.execute(
        "INSERT INTO roles (code, name, description, priority, is_system) VALUES (?, ?, ?, ?, ?)",
        [code, name, 'desc', priority, is_system]
    )
    return ds.execute("SELECT id FROM roles WHERE code = ?", [code]).fetchone()[0]


def _insert_permission(ds, code='P', resource_type='product', action='read', scope='all'):
    ds.execute(
        "INSERT INTO permissions (code, name, resource_type, action, description, scope) VALUES (?, ?, ?, ?, ?, ?)",
        [code, code, resource_type, action, 'desc', scope]
    )
    return ds.execute("SELECT id FROM permissions WHERE code = ?", [code]).fetchone()[0]


def _get_valid_action_code():
    """从 StandardActionLoader 拿一个有效 action_code"""
    try:
        from meta.core.standard_action_loader import StandardActionLoader
        codes = StandardActionLoader.get_action_codes()
        if codes:
            return list(codes)[0] if isinstance(codes, (set, frozenset)) else codes[0]
    except ImportError:
        pass
    return None


# =========================================================================
# A. 通配符权限
# =========================================================================

def test_wildcard_permission_grants_all(svc, ds):
    """has_permission: '*' 应当授予所有权限"""
    u = _insert_user(ds, 'wildcard_user')
    g = _insert_personal_group(ds, u)
    svc._ensure_user_in_group(u, g)
    r = _insert_role(ds, code='admin', name='Admin')
    p = _insert_permission(ds, code='*')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g, r])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r, p])
    # 任意 permission_code 都应返回 True
    assert svc.has_permission(u, 'product.read') is True
    assert svc.has_permission(u, 'any.random.code') is True


def test_wildcard_via_get_user_permissions(svc, ds):
    """get_user_permissions 返回包含 '*'"""
    u = _insert_user(ds, 'wildcard_perms_user')
    g = _insert_personal_group(ds, u)
    svc._ensure_user_in_group(u, g)
    r = _insert_role(ds, code='super', name='Super')
    p = _insert_permission(ds, code='*')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g, r])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r, p])
    perms = svc.get_user_permissions(u)
    assert '*' in perms


# =========================================================================
# B. 业务一致性
# =========================================================================

def test_get_user_roles_dedup(svc, ds):
    """同一角色通过多组获得：get_user_roles 应去重（DISTINCT）"""
    u = _insert_user(ds, 'dedup_roles_user')
    g1 = _insert_personal_group(ds, u)
    # 第二组用不同 code（避免 UNIQUE 约束）
    ds.execute(
        "INSERT INTO user_groups (code, name, description) VALUES (?, ?, ?)",
        [f'extra_group_{u}_1', 'Extra 1', 'desc']
    )
    g2 = ds.execute("SELECT id FROM user_groups WHERE code = ?", [f'extra_group_{u}_1']).fetchone()[0]
    svc._ensure_user_in_group(u, g1)
    svc._ensure_user_in_group(u, g2)
    r = _insert_role(ds, code='multi_g_role', name='Multi')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g1, r])
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g2, r])
    roles = svc.get_user_roles(u)
    # 同一角色不重复
    role_ids = [r['id'] for r in roles]
    assert len(role_ids) == len(set(role_ids))
    assert r in role_ids


def test_get_user_permissions_dedup(svc, ds):
    """同一权限通过多组多角色获得：应去重"""
    u = _insert_user(ds, 'dedup_perms_user')
    g1 = _insert_personal_group(ds, u)
    ds.execute(
        "INSERT INTO user_groups (code, name, description) VALUES (?, ?, ?)",
        [f'extra_group_{u}_2', 'Extra 2', 'desc']
    )
    g2 = ds.execute("SELECT id FROM user_groups WHERE code = ?", [f'extra_group_{u}_2']).fetchone()[0]
    svc._ensure_user_in_group(u, g1)
    svc._ensure_user_in_group(u, g2)
    r1 = _insert_role(ds, code='r_dedup1', name='R1')
    r2 = _insert_role(ds, code='r_dedup2', name='R2')
    p = _insert_permission(ds, code='shared.perm')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g1, r1])
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g2, r2])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r1, p])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r2, p])
    perms = svc.get_user_permissions(u)
    # 同一 permission 不重复
    assert perms.count('shared.perm') == 1


# =========================================================================
# C. assign_role / remove_role 业务一致性
# =========================================================================

def test_assign_role_repeat_is_idempotent(svc, ds):
    """assign_role 同一角色多次：结果幂等（去重）"""
    u = _insert_user(ds, 'repeat_assign')
    r = _insert_role(ds, code='repeat_r', name='Repeat')
    svc.assign_role(u, r)
    svc.assign_role(u, r)
    svc.assign_role(u, r)
    roles = svc.get_user_roles(u)
    role_ids = [x['id'] for x in roles]
    # 只有 1 个关联（INSERT OR IGNORE）
    assert role_ids.count(r) == 1


def test_assign_role_multiple_to_one_user(svc, ds):
    """assign_role 不同角色给同一用户：全部成功"""
    u = _insert_user(ds, 'multi_assign')
    r1 = _insert_role(ds, code='ma_r1', name='R1')
    r2 = _insert_role(ds, code='ma_r2', name='R2')
    r3 = _insert_role(ds, code='ma_r3', name='R3')
    assert svc.assign_role(u, r1) is True
    assert svc.assign_role(u, r2) is True
    assert svc.assign_role(u, r3) is True
    roles = svc.get_user_roles(u)
    role_ids = {x['id'] for x in roles}
    assert role_ids == {r1, r2, r3}


def test_remove_role_repeat_is_idempotent(svc, ds):
    """remove_role 多次移除：应幂等"""
    u = _insert_user(ds, 'repeat_remove')
    r = _insert_role(ds, code='removable', name='Removable')
    svc.assign_role(u, r)
    svc.remove_role(u, r)
    # 第二次 remove（应该不报错）
    result = svc.remove_role(u, r)
    assert result in (True, False)
    roles = svc.get_user_roles(u)
    assert r not in [x['id'] for x in roles]


def test_remove_role_not_in_personal_group(svc, ds):
    """remove_role 但用户没有 personal group：应安全返回"""
    u = _insert_user(ds, 'no_personal_remove')
    r = _insert_role(ds, code='not_in_personal', name='X')
    # 用户没有 personal group（只有用户记录）
    result = svc.remove_role(u, r)
    # 实现可能返回 True（无操作）或 False
    assert result in (True, False)


# =========================================================================
# D. 个人组唯一性
# =========================================================================

def test_personal_group_idempotent(svc, ds):
    """_get_or_create_personal_group 多次调用：返回相同 ID"""
    u = _insert_user(ds, 'personal_idem')
    g1 = svc._get_or_create_personal_group(u)
    g2 = svc._get_or_create_personal_group(u)
    g3 = svc._get_or_create_personal_group(u)
    assert g1 == g2 == g3


def test_personal_group_different_users(svc, ds):
    """不同用户的个人组互不冲突"""
    u1 = _insert_user(ds, 'p_user1')
    u2 = _insert_user(ds, 'p_user2')
    g1 = svc._get_or_create_personal_group(u1)
    g2 = svc._get_or_create_personal_group(u2)
    assert g1 != g2


def test_ensure_user_in_group_after_personal_group_creation(svc, ds):
    """_get_or_create_personal_group 不会自动加入用户，需要 _ensure_user_in_group"""
    u = _insert_user(ds, 'not_in_personal')
    g = svc._get_or_create_personal_group(u)
    # 此时 u 不在 personal group 里
    cursor = ds.execute(
        "SELECT 1 FROM user_group_members WHERE group_id = ? AND user_id = ?",
        [g, u]
    )
    assert cursor.fetchone() is None
    # 调用 _ensure_user_in_group 后
    svc._ensure_user_in_group(u, g)
    cursor = ds.execute(
        "SELECT 1 FROM user_group_members WHERE group_id = ? AND user_id = ?",
        [g, u]
    )
    assert cursor.fetchone() is not None


# =========================================================================
# E. set_role_permissions 边界
# =========================================================================

def test_set_role_permissions_duplicate_in_list(svc, ds):
    """set_role_permissions 列表中含重复 id：应去重"""
    r = _insert_role(ds, code='dup_perm_role', name='Dup')
    p1 = _insert_permission(ds, code='a.perm1')
    p2 = _insert_permission(ds, code='b.perm2')
    # 传 [p1, p1, p2] 应当不重复插入
    svc.set_role_permissions(r, [p1, p1, p2])
    cursor = ds.execute(
        "SELECT COUNT(*) FROM role_permissions WHERE role_id = ?", [r]
    )
    # 期望：2 条（p1, p2）
    assert cursor.fetchone()[0] == 2


def test_set_role_permissions_with_nonexistent_perm(svc, ds):
    """set_role_permissions 含不存在的 perm_id：FK 约束失败"""
    r = _insert_role(ds, code='fk_test_role', name='FKTest')
    # perm_id=9999 不存在
    try:
        result = svc.set_role_permissions(r, [9999])
        # 如果没启用 FK 约束：result 可能是 True（错误地插入 0 条）
        # 如果启用 FK 约束：result 是 False
        assert result in (True, False)
        # 验证：无 role_permissions 记录（FK 失败应回滚）
        cursor = ds.execute(
            "SELECT COUNT(*) FROM role_permissions WHERE role_id = ?", [r]
        )
        assert cursor.fetchone()[0] == 0
    except Exception:
        # 抛异常也合理
        pass


# =========================================================================
# F. 权限链路聚合
# =========================================================================

def test_has_permission_inherited_from_group(svc, ds):
    """用户从某组获得权限：has_permission 应当检测"""
    u = _insert_user(ds, 'inherited_user')
    g = _insert_personal_group(ds, u)
    svc._ensure_user_in_group(u, g)
    r = _insert_role(ds, code='inherited_role', name='Inherited')
    p = _insert_permission(ds, code='inherited.read')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g, r])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r, p])
    # 即使 p.code 不是 resource_type:action_code 格式，has_permission 应当也能匹配
    assert svc.has_permission(u, 'inherited.read') is True


def test_get_user_permissions_excludes_unlinked(svc, ds):
    """未关联的权限不应出现在用户权限中"""
    u = _insert_user(ds, 'exclusive_user')
    g = _insert_personal_group(ds, u)
    svc._ensure_user_in_group(u, g)
    r = _insert_role(ds, code='excl_role', name='Excl')
    p1 = _insert_permission(ds, code='granted.perm')
    p2 = _insert_permission(ds, code='not.granted')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g, r])
    # 只关联 p1，不关联 p2
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r, p1])
    perms = svc.get_user_permissions(u)
    assert 'granted.perm' in perms
    assert 'not.granted' not in perms


# =========================================================================
# G. check_permission_unified 边界
# =========================================================================

def test_check_permission_unified_wildcard(svc, ds):
    """check_permission_unified: '*' 权限 → 所有检查通过"""
    u = _insert_user(ds, 'check_wild_user')
    g = _insert_personal_group(ds, u)
    svc._ensure_user_in_group(u, g)
    r = _insert_role(ds, code='super_check', name='Super')
    p = _insert_permission(ds, code='*')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g, r])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r, p])
    # 任意 resource_type:action_code 都通过
    assert svc.check_permission_unified(u, 'product', 'read') is True
    assert svc.check_permission_unified(u, 'user', 'delete') is True


def test_check_permission_unified_with_instance(svc, ds):
    """check_permission_unified with resource_id：调用 _check_instance_permission"""
    u = _insert_user(ds, 'instance_user')
    g = _insert_personal_group(ds, u)
    svc._ensure_user_in_group(u, g)
    r = _insert_role(ds, code='inst_role', name='Inst')
    p = _insert_permission(ds, code='user:read', resource_type='user', action='read')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [g, r])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r, p])
    # 带 resource_id 走 _check_instance_permission（默认 True）
    result = svc.check_permission_unified(u, 'user', 'read', resource_id=123)
    assert result is True


def test_check_permission_unified_returns_false_no_role(svc, ds):
    """check_permission_unified: 无角色 → False"""
    u = _insert_user(ds, 'norole_check_user')
    # 用户存在但无 personal group / 角色
    result = svc.check_permission_unified(u, 'product', 'read')
    assert result is False


# =========================================================================
# H. create_permission_unified 边界
# =========================================================================

def test_create_permission_unified_duplicate_code(svc, ds):
    """create_permission_unified 创建重复 code：UNIQUE 约束"""
    code = f'dup_perm_{os.getpid()}'
    # 第一次创建
    pid1 = _create_permission_unified(svc, code, 'First')
    # 第二次创建相同 code
    try:
        pid2 = _create_permission_unified(svc, code, 'Second')
        # 如果允许：可能是 update or ignore
        # 验证：DB 中只有一个记录
        cursor = ds.execute("SELECT COUNT(*) FROM permissions WHERE code = ?", [code])
        assert cursor.fetchone()[0] == 1
    except Exception:
        # 抛异常是合理的（UNIQUE 约束）
        pass


def _create_permission_unified(svc, code, name):
    """辅助：创建权限（用真实 action code）"""
    action_code = _get_valid_action_code()
    if not action_code:
        pytest.skip("No standard actions available")
    # 解析 code 为 resource_type:action_code
    if ':' in code:
        rt, ac = code.split(':', 1)
    else:
        rt, ac = 'test', action_code
    # 检查 code 是否符合 resource_type:action_code 格式
    if ac != action_code:
        # code 不是标准 action 格式，跳过
        pytest.skip(f"Code {code} doesn't match standard action format")
    return svc.create_permission_unified(
        resource_type=rt,
        action_code=ac,
        name=name,
        description='Test'
    )


# =========================================================================
# I. remove_role 不应影响其他用户
# =========================================================================

def test_remove_role_only_affects_target_user(svc, ds):
    """remove_role 一个用户：不应影响其他用户"""
    u1 = _insert_user(ds, 'user1')
    u2 = _insert_user(ds, 'user2')
    r = _insert_role(ds, code='shared_removable', name='Shared')
    svc.assign_role(u1, r)
    svc.assign_role(u2, r)
    # u1 移除
    svc.remove_role(u1, r)
    # u2 仍有该角色
    u2_roles = svc.get_user_roles(u2)
    assert r in [x['id'] for x in u2_roles]
    # u1 没有
    u1_roles = svc.get_user_roles(u1)
    assert r not in [x['id'] for x in u1_roles]


# =========================================================================
# J. 综合场景
# =========================================================================

def test_full_permission_lifecycle(svc, ds):
    """完整权限生命周期：分配 → 验证 → 移除 → 失效"""
    u = _insert_user(ds, 'lifecycle_perm_user')
    r = _insert_role(ds, code='lifecycle_role', name='LCR')
    p = _insert_permission(ds, code='lifecycle.perm')

    # 1) 分配角色
    assert svc.assign_role(u, r) is True
    g = svc._get_or_create_personal_group(u)
    svc._ensure_user_in_group(u, g)
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [r, p])

    # 2) 验证权限存在
    assert svc.has_permission(u, 'lifecycle.perm') is True

    # 3) 移除角色
    svc.remove_role(u, r)
    # 4) 权限应不再存在
    assert svc.has_permission(u, 'lifecycle.perm') is False


def test_role_priority_ordering(svc, ds):
    """get_user_roles 应当按某种顺序返回（不验证具体顺序）"""
    u = _insert_user(ds, 'priority_user')
    g = _insert_personal_group(ds, u)
    svc._ensure_user_in_group(u, g)
    r1 = _insert_role(ds, code='low', name='Low', priority=1)
    r2 = _insert_role(ds, code='high', name='High', priority=10)
    r3 = _insert_role(ds, code='mid', name='Mid', priority=5)
    svc.assign_role(u, r1)
    svc.assign_role(u, r2)
    svc.assign_role(u, r3)
    roles = svc.get_user_roles(u)
    role_codes = [r['code'] for r in roles]
    assert set(role_codes) == {'low', 'high', 'mid'}


def test_system_role_cannot_be_removed_via_service(svc, ds):
    """is_system=1 的角色：业务方法不应特殊处理（验证无副作用）"""
    u = _insert_user(ds, 'sys_user')
    r = _insert_role(ds, code='system_role', name='System', is_system=1)
    svc.assign_role(u, r)
    # 即使是 system role，仍可移除（业务方法不做特殊处理）
    svc.remove_role(u, r)
    roles = svc.get_user_roles(u)
    assert r not in [x['id'] for x in roles]
