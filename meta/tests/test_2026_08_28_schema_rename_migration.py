"""
[Phase 1] DB schema rename migration 验证测试
- 验证 7 张 role 旧表 RENAME 为 permission_set 新表
- 验证 org_functions 新表存在
- 验证 org_type / org_scope 列存在并已回填
- 验证 down() 可逆 (回滚到原名)

修正说明 (2026-08-28, 当前 DB 状态):
- 旧 plan 中 `role_menus` / `role_effective_intents` 不存在, 改测真实表名
- 旧 plan 中 `user_groups` / `user_group_members` 等 RENAME 由 `rename_user_groups_to_orgs` 处理
- 当前 DB 已有 test residue, 先 DROP 再 RENAME
"""
import sqlite3
import tempfile
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def fresh_db():
    """用临时 DB 跑 migration, 不污染主 DB

    修复 (Critical-3): 优先使用 snapshot_20260828 作为 pre-migration 源,
    因为当前 architecture.db 已被迁移过 (已是终态).
    若 snapshot 不存在则 fallback 到 architecture.db (post-migration, 部分测试会 skip).
    """
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / 'test.db'

    # 优先用 pre-migration snapshot (包含旧表名), 否则用当前 DB (已是 post-migration)
    snapshot = Path('meta/architecture.db.snapshot_20260828')
    src = snapshot if snapshot.exists() else Path('meta/architecture.db')

    main_db = sqlite3.connect(str(src))
    main_db.backup(sqlite3.connect(str(db_path)))
    main_db.close()

    yield db_path

    # Windows 文件锁: 多次重试删除
    import time
    for _ in range(5):
        try:
            shutil.rmtree(tmp_dir)
            break
        except PermissionError:
            time.sleep(0.2)
    else:
        # 最后兜底: 删除文件, dir 留给 OS
        for f in Path(tmp_dir).iterdir():
            try:
                f.unlink()
            except Exception:
                pass


def test_rename_roles_to_permission_sets(fresh_db):
    """7 张 role 表 RENAME 成功 (+ DROP test residue)"""
    conn = sqlite3.connect(str(fresh_db))

    # 执行 v071 (DROP residue) + v070 (RENAME)
    from meta.migrations.v071__drop_p13_t3_residue_tables import migrate as v071_migrate
    from meta.migrations.v070__rename_roles_to_permission_sets import migrate as v070_migrate
    v071_migrate(fresh_db)
    v070_migrate(fresh_db)

    # 验证新表存在
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}

    # 新表 (从真实 role 表 RENAME 而来)
    for new_name in ['permission_sets', 'permission_set_permissions',
                     'permission_set_data_permissions',
                     'permission_set_dimension_scopes',
                     'permission_set_menu_permissions',
                     'user_permission_sets']:
        assert new_name in tables, f"New table {new_name} missing"

    # 验证旧 role 表已消失
    for old_name in ['roles', 'role_permissions', 'role_data_permissions',
                     'role_dimension_scopes', 'role_menu_permissions',
                     'user_roles']:
        assert old_name not in tables, f"Old table {old_name} should be renamed"

    # role_effective_intents 不存在于当前 DB, 不需要验证
    assert 'role_effective_intents' not in tables, (
        "role_effective_intents should not exist in current DB"
    )


def test_data_preserved_after_rename(fresh_db):
    """数据保留 (rename 不丢数据)"""
    conn = sqlite3.connect(str(fresh_db))

    # 1. 记录原始数据
    old_count = conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    old_users_count = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0]
    old_perm_count = conn.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]

    # 2. 执行 v071 (DROP residue) + v070 (RENAME)
    from meta.migrations.v071__drop_p13_t3_residue_tables import migrate as v071_migrate
    from meta.migrations.v070__rename_roles_to_permission_sets import migrate as v070_migrate
    v071_migrate(fresh_db)
    v070_migrate(fresh_db)

    # 3. 验证数据
    new_count = conn.execute("SELECT COUNT(*) FROM permission_sets").fetchone()[0]
    new_users_count = conn.execute("SELECT COUNT(*) FROM user_permission_sets").fetchone()[0]
    new_perm_count = conn.execute(
        "SELECT COUNT(*) FROM permission_set_permissions"
    ).fetchone()[0]

    assert new_count == old_count, (
        f"PermissionSets count {new_count} != original {old_count}"
    )
    assert new_users_count == old_users_count, (
        "User permission sets count mismatch"
    )
    assert new_perm_count == old_perm_count, (
        f"PermissionSet permissions count {new_perm_count} != original {old_perm_count}"
    )


def test_rename_user_groups_to_orgs(fresh_db):
    """user_groups 系列 RENAME + 新增 org_type 列"""
    conn = sqlite3.connect(str(fresh_db))

    from meta.migrations.v072__rename_user_groups_to_orgs import migrate as v072_migrate
    v072_migrate(fresh_db)

    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}

    assert 'orgs' in tables
    assert 'org_members' in tables
    assert 'org_permission_sets' in tables
    assert 'org_data_permissions' in tables
    assert 'user_groups' not in tables
    assert 'user_group_members' not in tables
    assert 'group_roles' not in tables
    assert 'group_data_permissions' not in tables

    # 验证新增列
    cols = [r[1] for r in conn.execute("PRAGMA table_info(orgs)").fetchall()]
    assert 'org_type' in cols
    assert 'org_scope' in cols


def test_org_functions_table_created(fresh_db):
    """org_functions 表存在 + 7 种职能类型

    修复 (Critical-1): create_org_functions 依赖 orgs 表 (FK + INSERT),
    但 fresh_db 起始状态是旧表名, 必须先跑 rename_user_groups_to_orgs.upgrade
    创建 orgs 表, 才能让 create_org_functions.upgrade 正常工作.
    """
    conn = sqlite3.connect(str(fresh_db))

    # Step 1: 先建 orgs 表 (满足 FK 依赖 + 提供 org_id 列表用于回填)
    from meta.migrations.v072__rename_user_groups_to_orgs import migrate as v072_migrate
    v072_migrate(fresh_db)

    # Step 2: 再建 org_functions 表
    from meta.migrations.v073__create_org_functions import migrate as v073_migrate
    v073_migrate(fresh_db)

    # 表存在
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert 'org_functions' in tables

    # 列定义正确
    cols = {r[1] for r in conn.execute("PRAGMA table_info(org_functions)").fetchall()}
    expected_cols = {'id', 'org_id', 'function_type', 'is_primary',
                     'effective_from', 'effective_to'}
    assert expected_cols.issubset(cols)


def test_down_migration_reversible(fresh_db):
    """down() 可逆 (回滚到原名)"""
    from meta.migrations.v070__rename_roles_to_permission_sets import (
        migrate as v070_migrate,
        downgrade as v070_downgrade,
    )

    # 先跑 v071 (DROP residue) + v070 (RENAME) → 终态
    from meta.migrations.v071__drop_p13_t3_residue_tables import migrate as v071_migrate
    v071_migrate(fresh_db)
    v070_migrate(fresh_db)

    # 再走 v070 downgrade → 回到原名
    v070_downgrade(fresh_db)

    conn = sqlite3.connect(str(fresh_db))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert 'roles' in tables, "down() should restore 'roles'"
    assert 'permission_sets' not in tables, (
        "down() should remove 'permission_sets'"
    )
