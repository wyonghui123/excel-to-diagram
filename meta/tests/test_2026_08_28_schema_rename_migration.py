# -*- coding: utf-8 -*-
# ALLOW_RAW_SQL: 本文件含裸 SQL 构造迁移测试数据/DDL，守卫豁免（2026-11-09 恢复覆盖）
"""
[Phase 1] DB schema rename migration 验证测试

覆盖:
- v070: roles 系列 6 张表 → permission_set_* / user_permission_sets
- v072: user_groups 系列 4 张表 → org* + 新增 org_type / org_scope 列
- v073: org_functions 新表 + administrative 默认职能回填
- downgrade 可逆

说明:
- 旧版本此测试直接复制主库再跑迁移；主库已是终态（无旧表），
  迁移会全部跳过，测试失去意义。现改为按旧版 schema 现场建库。
"""
import sqlite3
import tempfile
import shutil
from pathlib import Path

import pytest

from meta.migrations import v070__rename_roles_to_permission_sets as v070
from meta.migrations import v072__rename_user_groups_to_orgs as v072
from meta.migrations import v073__create_org_functions as v073


LEGACY_DDL = """
CREATE TABLE roles (id INTEGER PRIMARY KEY, code TEXT, name TEXT);
CREATE TABLE role_permissions (role_id INTEGER, permission_id INTEGER);
CREATE TABLE role_data_permissions (role_id INTEGER, data_scope TEXT);
CREATE TABLE role_dimension_scopes (role_id INTEGER, dimension_type TEXT);
CREATE TABLE role_menu_permissions (role_id INTEGER, menu_code TEXT);
CREATE TABLE user_roles (user_id INTEGER, role_id INTEGER);
CREATE TABLE user_groups (id INTEGER PRIMARY KEY, code TEXT, name TEXT);
CREATE TABLE user_group_members (group_id INTEGER, user_id INTEGER);
CREATE TABLE group_roles (group_id INTEGER, role_id INTEGER);
CREATE TABLE group_data_permissions (group_id INTEGER, data_scope TEXT);
"""

LEGACY_DATA = """
INSERT INTO roles (id, code, name) VALUES (1, 'admin', '管理员');
INSERT INTO roles (id, code, name) VALUES (2, 'viewer', '只读');
INSERT INTO user_roles (user_id, role_id) VALUES (1, 1);
INSERT INTO user_roles (user_id, role_id) VALUES (2, 2);
INSERT INTO role_permissions (role_id, permission_id) VALUES (1, 10);
INSERT INTO role_permissions (role_id, permission_id) VALUES (1, 11);
INSERT INTO role_permissions (role_id, permission_id) VALUES (2, 10);
INSERT INTO user_groups (id, code, name) VALUES (1, 'dept_a', '研发部');
INSERT INTO user_groups (id, code, name) VALUES (2, 'team_b', '测试组');
INSERT INTO user_group_members (group_id, user_id) VALUES (1, 1);
INSERT INTO group_roles (group_id, role_id) VALUES (1, 1);
"""


@pytest.fixture
def fresh_db():
    """旧版 schema 的临时 DB，不污染主库"""
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / 'legacy.db'
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(LEGACY_DDL)
        conn.executescript(LEGACY_DATA)
        conn.commit()
    finally:
        conn.close()

    yield db_path

    for _ in range(5):
        try:
            shutil.rmtree(tmp_dir)
            break
        except PermissionError:
            import time
            time.sleep(0.2)
    else:
        for f in Path(tmp_dir).iterdir():
            try:
                f.unlink()
            except Exception:
                pass


def _tables(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()


def test_rename_roles_to_permission_sets(fresh_db):
    """6 张 role 旧表 RENAME 成功"""
    assert v070.migrate(fresh_db) is True
    tables = _tables(fresh_db)

    for new_name in ['permission_sets', 'permission_set_permissions',
                     'permission_set_data_permissions',
                     'permission_set_dimension_scopes',
                     'permission_set_menu_permissions',
                     'user_permission_sets']:
        assert new_name in tables, f"New table {new_name} missing"

    for old_name in ['roles', 'role_permissions', 'role_data_permissions',
                     'role_dimension_scopes', 'role_menu_permissions',
                     'user_roles']:
        assert old_name not in tables, f"Old table {old_name} should be renamed"


def test_data_preserved_after_rename(fresh_db):
    """RENAME 不丢数据"""
    conn = sqlite3.connect(str(fresh_db))
    old_count = conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    old_users_count = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0]
    old_perm_count = conn.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]
    conn.close()

    assert v070.migrate(fresh_db) is True

    conn = sqlite3.connect(str(fresh_db))
    try:
        new_count = conn.execute("SELECT COUNT(*) FROM permission_sets").fetchone()[0]
        new_users_count = conn.execute(
            "SELECT COUNT(*) FROM user_permission_sets"
        ).fetchone()[0]
        new_perm_count = conn.execute(
            "SELECT COUNT(*) FROM permission_set_permissions"
        ).fetchone()[0]
    finally:
        conn.close()

    assert new_count == old_count
    assert new_users_count == old_users_count
    assert new_perm_count == old_perm_count


def test_rename_user_groups_to_orgs(fresh_db):
    """user_groups 系列 RENAME + 新增 org_type / org_scope 列"""
    assert v072.migrate(fresh_db) is True
    tables = _tables(fresh_db)

    assert 'orgs' in tables
    assert 'org_members' in tables
    assert 'org_permission_sets' in tables
    assert 'org_data_permissions' in tables
    assert 'user_groups' not in tables
    assert 'user_group_members' not in tables
    assert 'group_roles' not in tables
    assert 'group_data_permissions' not in tables

    conn = sqlite3.connect(str(fresh_db))
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(orgs)").fetchall()]
    finally:
        conn.close()
    assert 'org_type' in cols
    assert 'org_scope' in cols


def test_org_functions_table_created(fresh_db):
    """org_functions 表 + administrative 默认职能回填"""
    assert v072.migrate(fresh_db) is True
    assert v073.migrate(fresh_db) is True

    assert 'org_functions' in _tables(fresh_db)

    conn = sqlite3.connect(str(fresh_db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(org_functions)").fetchall()}
        admin_rows = conn.execute(
            "SELECT COUNT(*) FROM org_functions "
            "WHERE function_type = 'administrative' AND is_primary = 1"
        ).fetchone()[0]
        org_count = conn.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
    finally:
        conn.close()

    assert {'id', 'org_id', 'function_type', 'is_primary',
            'effective_from', 'effective_to'}.issubset(cols)
    assert admin_rows == org_count


def test_down_migration_reversible(fresh_db):
    """downgrade 可逆（恢复 roles）"""
    assert v070.migrate(fresh_db) is True
    assert v070.downgrade(fresh_db) is True
    tables = _tables(fresh_db)
    assert 'roles' in tables
    assert 'permission_sets' not in tables
