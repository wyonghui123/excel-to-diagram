"""
[Phase 1] Plan A 端到端验证测试

修正说明 (2026-08-28, 当前 DB 状态):
- 11 张 role/user_group 旧表已经 RENAME 完毕
- role_effective_intents 不存在 (跳过)
- role_intents / roles_v1_backup 不在 spec 范围
"""
import sqlite3


def test_11_old_tables_renamed():
    """10 张旧 role/user_group 表全部消失 (role_effective_intents 不存在)"""
    conn = sqlite3.connect('meta/architecture.db')
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    old_tables = [
        'roles', 'role_permissions', 'role_data_permissions',
        'role_dimension_scopes', 'role_menu_permissions',
        'user_roles', 'user_groups', 'user_group_members',
        'group_roles', 'group_data_permissions',
    ]

    for old_name in old_tables:
        assert old_name not in tables, (
            f"Old table {old_name} still exists"
        )


def test_11_new_tables_exist():
    """10 张新表全部存在"""
    conn = sqlite3.connect('meta/architecture.db')
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    new_tables = [
        'permission_sets', 'permission_set_permissions',
        'permission_set_data_permissions', 'permission_set_dimension_scopes',
        'permission_set_menu_permissions',
        'user_permission_sets', 'orgs', 'org_members',
        'org_permission_sets', 'org_data_permissions',
    ]

    for new_name in new_tables:
        assert new_name in tables, f"New table {new_name} missing"


def test_org_functions_table_exists_with_default_data():
    """org_functions 表存在 + 默认 administrative 主职能数据"""
    conn = sqlite3.connect('meta/architecture.db')

    # 表存在
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert 'org_functions' in tables

    # 默认数据: 所有 org 都有 administrative 主职能
    org_count = conn.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
    admin_count = conn.execute(
        "SELECT COUNT(*) FROM org_functions "
        "WHERE function_type='administrative' AND is_primary=1"
    ).fetchone()[0]

    assert admin_count >= org_count, (
        f"Administrative count {admin_count} < org count {org_count}"
    )


def test_orgs_table_has_org_type_and_scope():
    """orgs 表有 org_type / org_scope 列"""
    conn = sqlite3.connect('meta/architecture.db')
    cols = {r[1] for r in conn.execute("PRAGMA table_info(orgs)").fetchall()}

    assert 'org_type' in cols
    assert 'org_scope' in cols


def test_data_preserved_no_loss():
    """数据无丢失 (snapshot vs 当前对比)"""
    snap = sqlite3.connect('meta/architecture.db.snapshot_20260828')
    cur = sqlite3.connect('meta/architecture.db')

    comparisons = [
        ('roles', 'permission_sets'),
        ('user_groups', 'orgs'),
        ('user_roles', 'user_permission_sets'),
        ('user_group_members', 'org_members'),
        ('role_permissions', 'permission_set_permissions'),
        ('role_data_permissions', 'permission_set_data_permissions'),
        ('role_dimension_scopes', 'permission_set_dimension_scopes'),
        ('role_menu_permissions', 'permission_set_menu_permissions'),
        ('group_roles', 'org_permission_sets'),
        ('group_data_permissions', 'org_data_permissions'),
    ]

    for old, new in comparisons:
        old_count = snap.execute(
            f"SELECT COUNT(*) FROM {old}"
        ).fetchone()[0]
        new_count = cur.execute(
            f"SELECT COUNT(*) FROM {new}"
        ).fetchone()[0]
        assert old_count == new_count, (
            f"{old}={old_count} vs {new}={new_count}"
        )
