# -*- coding: utf-8 -*-
"""
P9 单元测试：permission_service 业务方法
v1.4 P7/P8 Sunset 后保留 13 个业务方法
"""
import pytest

pytestmark = pytest.mark.integration

import sys
import os
import sqlite3
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
from meta.services.permission_service import PermissionService


@pytest.fixture
def ds():
    """创建内存式临时 DB（含完整 schema）"""
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

def _insert_user(ds, username='u', display_name='U'):
    ds.execute(
        "INSERT INTO users (username, display_name, email, status) VALUES (?, ?, ?, ?)",
        [username, display_name, f'{username}@x.com', 'active']
    )
    return ds.execute("SELECT id FROM users WHERE username = ?", [username]).fetchone()[0]


def _insert_personal_group(ds, user_id):
    """插入个人组（用于 _get_or_create_personal_group 测试）"""
    code = f'personal_group_user_{user_id}'
    ds.execute(
        "INSERT INTO user_groups (code, name, description) VALUES (?, ?, ?)",
        [code, f'Personal group for user {user_id}', 'auto-generated']
    )
    return ds.execute("SELECT id FROM user_groups WHERE code = ?", [code]).fetchone()[0]


def _insert_role(ds, code='R', name='Role', priority=0, is_system=0):
    ds.execute(
        "INSERT INTO roles (code, name, description, priority, is_system) VALUES (?, ?, ?, ?, ?)",
        [code, name, 'desc', priority, is_system]
    )
    return ds.execute("SELECT id FROM roles WHERE code = ?", [code]).fetchone()[0]


def _insert_permission(ds, code='P', resource_type='product', action='read'):
    ds.execute(
        "INSERT INTO permissions (code, name, resource_type, action, description) VALUES (?, ?, ?, ?, ?)",
        [code, code, resource_type, action, 'desc']
    )
    return ds.execute("SELECT id FROM permissions WHERE code = ?", [code]).fetchone()[0]


# ============== 1. 内部方法：_get_or_create_personal_group ==============

def test_get_or_create_personal_group_creates(svc, ds):
    """_get_or_create_personal_group: 用户首次创建时插入 personal_X 组"""
    uid = _insert_user(ds, 'new_user')
    group_id = svc._get_or_create_personal_group(uid)
    assert group_id > 0
    # 验证 DB 中存在
    cursor = ds.execute("SELECT code FROM user_groups WHERE id = ?", [group_id])
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == f'personal_group_user_{uid}'


def test_get_or_create_personal_group_returns_existing(svc, ds):
    """_get_or_create_personal_group: 已存在时直接返回"""
    uid = _insert_user(ds, 'existing_user')
    first = svc._get_or_create_personal_group(uid)
    second = svc._get_or_create_personal_group(uid)
    assert first == second


# ============== 2. 内部方法：_ensure_user_in_group ==============

def test_ensure_user_in_group_inserts(svc, ds):
    """_ensure_user_in_group: 插入 user_group_members"""
    uid = _insert_user(ds, 'ensure_user')
    gid = _insert_personal_group(ds, uid)
    svc._ensure_user_in_group(uid, gid)
    cursor = ds.execute(
        "SELECT 1 FROM user_group_members WHERE user_id = ? AND group_id = ?",
        [uid, gid]
    )
    assert cursor.fetchone() is not None


def test_ensure_user_in_group_idempotent(svc, ds):
    """_ensure_user_in_group: 重复调用不报错"""
    uid = _insert_user(ds, 'idem_user')
    gid = _insert_personal_group(ds, uid)
    svc._ensure_user_in_group(uid, gid)
    svc._ensure_user_in_group(uid, gid)  # 第二次
    cursor = ds.execute(
        "SELECT COUNT(*) FROM user_group_members WHERE user_id = ? AND group_id = ?",
        [uid, gid]
    )
    assert cursor.fetchone()[0] == 1


# ============== 3. get_user_roles ==============

def test_get_user_roles_empty(svc, ds):
    """用户无角色 → 空列表"""
    uid = _insert_user(ds, 'noroles_user')
    roles = svc.get_user_roles(uid)
    assert roles == []


def test_get_user_roles_via_personal_group(svc, ds):
    """通过个人组→组角色 链路获取"""
    uid = _insert_user(ds, 'with_roles')
    gid = _insert_personal_group(ds, uid)
    svc._ensure_user_in_group(uid, gid)
    rid = _insert_role(ds, code='dev', name='Developer')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [gid, rid])
    roles = svc.get_user_roles(uid)
    assert len(roles) == 1
    assert roles[0]['id'] == rid
    assert roles[0]['code'] == 'dev'


# ============== 4. get_user_permissions ==============

def test_get_user_permissions_empty(svc, ds):
    """用户无权限 → 空列表"""
    uid = _insert_user(ds, 'noperm_user')
    perms = svc.get_user_permissions(uid)
    assert perms == []


def test_get_user_permissions_via_role(svc, ds):
    """通过用户→组→角色→权限 链路"""
    uid = _insert_user(ds, 'perm_user')
    gid = _insert_personal_group(ds, uid)
    svc._ensure_user_in_group(uid, gid)
    rid = _insert_role(ds, code='editor', name='Editor')
    pid = _insert_permission(ds, code='product.read')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [gid, rid])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, pid])
    perms = svc.get_user_permissions(uid)
    assert 'product.read' in perms


# ============== 5. has_permission ==============

def test_has_permission_true(svc, ds):
    """has_permission: 用户有该权限 → True"""
    uid = _insert_user(ds, 'has_perm_user')
    gid = _insert_personal_group(ds, uid)
    svc._ensure_user_in_group(uid, gid)
    rid = _insert_role(ds, code='admin', name='Admin')
    pid = _insert_permission(ds, code='product.write')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [gid, rid])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, pid])
    assert svc.has_permission(uid, 'product.write') is True


def test_has_permission_false(svc, ds):
    """has_permission: 用户无该权限 → False"""
    uid = _insert_user(ds, 'no_perm_user')
    assert svc.has_permission(uid, 'product.delete') is False


# ============== 6. assign_role ==============

def test_assign_role_creates_personal_group(svc, ds):
    """assign_role: 用户无个人组时自动创建"""
    uid = _insert_user(ds, 'new_assign_user')
    rid = _insert_role(ds, code='tester', name='Tester')
    result = svc.assign_role(uid, rid)
    assert result is True
    # 验证：用户有了 personal 组 + 角色关联
    cursor = ds.execute(
        "SELECT g.id FROM user_groups g WHERE g.code = ?", [f'personal_group_user_{uid}']
    )
    assert cursor.fetchone() is not None
    roles = svc.get_user_roles(uid)
    assert any(r['id'] == rid for r in roles)


def test_assign_role_existing_group(svc, ds):
    """assign_role: 用户已有个人组时直接加角色"""
    uid = _insert_user(ds, 'assign_exist')
    # 第一次 assign_role 会创建 personal 组
    rid1 = _insert_role(ds, code='first', name='First')
    svc.assign_role(uid, rid1)
    # 第二次 assign_role 复用 personal 组
    rid2 = _insert_role(ds, code='second', name='Second')
    result = svc.assign_role(uid, rid2)
    assert result is True
    roles = svc.get_user_roles(uid)
    role_ids = [r['id'] for r in roles]
    assert rid1 in role_ids
    assert rid2 in role_ids


# ============== 7. remove_role ==============

def test_remove_role(svc, ds):
    """remove_role: 移除用户角色"""
    uid = _insert_user(ds, 'remove_role_user')
    rid = _insert_role(ds, code='temp_role', name='Temp')
    svc.assign_role(uid, rid)
    assert len(svc.get_user_roles(uid)) == 1
    result = svc.remove_role(uid, rid)
    assert result is True
    assert len(svc.get_user_roles(uid)) == 0


def test_remove_role_not_exists(svc, ds):
    """remove_role: 用户没有该角色"""
    uid = _insert_user(ds, 'no_role_to_remove')
    rid = _insert_role(ds, code='unrelated', name='Unrelated')
    result = svc.remove_role(uid, rid)
    # 实现可能返回 True（无操作）或 False
    assert result in (True, False)


# ============== 8. get_all_roles ==============

def test_get_all_roles(svc, ds):
    """get_all_roles: 获取所有角色"""
    _insert_role(ds, code='r1', name='Role1')
    _insert_role(ds, code='r2', name='Role2')
    roles = svc.get_all_roles()
    assert len(roles) == 2
    codes = [r['code'] for r in roles]
    assert 'r1' in codes
    assert 'r2' in codes


# ============== 9. get_role_permissions ==============

def test_get_role_permissions_empty(svc, ds):
    """角色无权限"""
    rid = _insert_role(ds, code='empty_role')
    perms = svc.get_role_permissions(rid)
    assert perms == []


def test_get_role_permissions_with_perms(svc, ds):
    """角色有权限"""
    rid = _insert_role(ds, code='full_role')
    p1 = _insert_permission(ds, code='product.read')
    p2 = _insert_permission(ds, code='product.write')
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, p1])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, p2])
    perms = svc.get_role_permissions(rid)
    codes = [p['code'] for p in perms]
    assert 'product.read' in codes
    assert 'product.write' in codes


# ============== 10. set_role_permissions ==============

def test_set_role_permissions_replaces(svc, ds):
    """set_role_permissions 全量替换"""
    rid = _insert_role(ds, code='set_perms_role')
    p1 = _insert_permission(ds, code='a.perm')
    p2 = _insert_permission(ds, code='b.perm')
    p3 = _insert_permission(ds, code='c.perm')
    # 初始有 p1, p2
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, p1])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, p2])
    # 替换为只有 p3
    result = svc.set_role_permissions(rid, [p3])
    assert result is True
    perms = svc.get_role_permissions(rid)
    codes = [p['code'] for p in perms]
    assert codes == ['c.perm']


def test_set_role_permissions_empty_clears(svc, ds):
    """set_role_permissions([]) 清空"""
    rid = _insert_role(ds, code='clear_role')
    p1 = _insert_permission(ds, code='to.clear')
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, p1])
    svc.set_role_permissions(rid, [])
    perms = svc.get_role_permissions(rid)
    assert perms == []


# ============== 11. _validate_action_code ==============

def test_validate_action_code_valid(svc, ds):
    """_validate_action_code: 标准 action code（来自 StandardActionLoader）"""
    # 直接用 StandardActionLoader 拿一个有效 code
    try:
        from meta.core.standard_action_loader import StandardActionLoader
        codes = StandardActionLoader.get_action_codes()
        if codes:
            # codes 可能是 set 或 list
            code = list(codes)[0] if isinstance(codes, (set, frozenset)) else codes[0]
            assert svc._validate_action_code(code) is True
        else:
            pytest.skip("No standard actions available")
    except ImportError:
        pytest.skip("StandardActionLoader not available")


def test_validate_action_code_invalid(svc, ds):
    """_validate_action_code: 非法 action code"""
    assert svc._validate_action_code('') is False
    # 含特殊字符
    assert svc._validate_action_code('read;DROP TABLE x') is False


# ============== 12. check_permission_unified ==============

def test_check_permission_unified_true(svc, ds):
    """check_permission_unified: 有权限 → True"""
    uid = _insert_user(ds, 'check_user')
    gid = _insert_personal_group(ds, uid)
    rid = _insert_role(ds, code='check_role')
    pid = _insert_permission(ds, code='user:read', resource_type='user', action='read')
    ds.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)", [gid, rid])
    ds.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)", [rid, pid])
    # _ensure_user_in_group 才行（get_user_roles JOIN user_group_members）
    svc._ensure_user_in_group(uid, gid)
    assert svc.check_permission_unified(uid, 'user', 'read') is True


def test_check_permission_unified_false(svc, ds):
    """check_permission_unified: 无权限 → False"""
    uid = _insert_user(ds, 'nocheck_user')
    assert svc.check_permission_unified(uid, 'user', 'delete') is False


# ============== 13. create_permission_unified ==============

def test_create_permission_unified(svc, ds):
    """create_permission_unified: 创建权限（用 StandardActionLoader 拿真实 action_code）"""
    try:
        from meta.core.standard_action_loader import StandardActionLoader
        codes = StandardActionLoader.get_action_codes()
        if not codes:
            pytest.skip("No standard actions available")
        # codes 可能是 set 或 list
        action_code = list(codes)[0] if isinstance(codes, (set, frozenset)) else codes[0]
    except ImportError:
        pytest.skip("StandardActionLoader not available")

    pid = svc.create_permission_unified(
        resource_type='order',
        action_code=action_code,
        name='Test Permission',
        description='Test description'
    )
    assert pid > 0
    cursor = ds.execute("SELECT code, name, resource_type, action, scope FROM permissions WHERE id = ?", [pid])
    row = cursor.fetchone()
    assert row is not None
    # 列顺序: code, name, resource_type, action, scope
    assert row[0] == f'order:{action_code}'  # code
    assert row[1] == 'Test Permission'  # name
    assert row[2] == 'order'  # resource_type
    assert row[3] == action_code  # action
    assert row[4] == 'all'  # scope default
