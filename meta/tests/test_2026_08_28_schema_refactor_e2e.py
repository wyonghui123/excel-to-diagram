"""
[Phase 1] Plan A 端到端验证测试 (fresh_db 隔离版)

修正说明 (2026-08-30):
- 原版直接连 meta/architecture.db 断言新表存在, 但主 DB 尚未执行迁移
  (3 个迁移脚本就绪未执行), 直接跑必然失败
- 改为 fresh_db 隔离: 从主 DB backup 出临时库 → 按依赖顺序执行完整迁移链 →
  验证端到端结果, 不污染主 DB
- 数据保留对比改为"迁移前 vs 迁移后"计数, 不再依赖
  meta/architecture.db.snapshot_20260828 (该快照与当前主 DB 状态不同步)

迁移链执行顺序 (与 runner prerequisites 声明一致):
  1. rename_roles_to_permission_sets  (roles 系列 → permission_sets 系列)
  2. rename_user_groups_to_orgs       (user_groups 系列 → orgs 系列)
  3. create_org_functions             (依赖 orgs 表存在)
"""
import sqlite3
import tempfile
import shutil
import time
from pathlib import Path
import pytest

MIGRATION_ORDER = [
    'rename_roles_to_permission_sets',
    'rename_user_groups_to_orgs',
    'create_org_functions',
]

OLD_TABLES = [
    'roles', 'role_permissions', 'role_data_permissions',
    'role_dimension_scopes', 'role_menu_permissions',
    'user_roles', 'user_groups', 'user_group_members',
    'group_roles', 'group_data_permissions',
]

NEW_TABLES = [
    'permission_sets', 'permission_set_permissions',
    'permission_set_data_permissions', 'permission_set_dimension_scopes',
    'permission_set_menu_permissions',
    'user_permission_sets', 'orgs', 'org_members',
    'org_permission_sets', 'org_data_permissions',
]

DATA_COMPARISONS = [
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


@pytest.fixture
def fresh_db():
    """从主 DB backup 创建临时库, 不污染主 DB"""
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / 'test.db'

    main_db = sqlite3.connect('meta/architecture.db')
    main_db.backup(sqlite3.connect(str(db_path)))
    main_db.close()

    yield db_path

    # Windows 文件锁: 多次重试删除
    for _ in range(5):
        try:
            shutil.rmtree(tmp_dir)
            break
        except PermissionError:
            time.sleep(0.2)
    else:
        for f in Path(tmp_dir).iterdir():
            try:
                f.unlink()
            except Exception:
                pass


def _run_full_migration_chain(db_path):
    """按依赖顺序执行 3 个迁移 (验证完整迁移链端到端)"""
    conn = sqlite3.connect(str(db_path))
    try:
        for name in MIGRATION_ORDER:
            module = __import__(f'meta.migrations.{name}', fromlist=['upgrade'])
            module.upgrade(conn)
    finally:
        conn.close()


def _table_set(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()


def test_11_old_tables_renamed(fresh_db):
    """10 张旧 role/user_group 表全部消失 (role_effective_intents 不存在)"""
    _run_full_migration_chain(fresh_db)
    tables = _table_set(fresh_db)

    for old_name in OLD_TABLES:
        assert old_name not in tables, f"Old table {old_name} still exists"


def test_11_new_tables_exist(fresh_db):
    """10 张新表全部存在"""
    _run_full_migration_chain(fresh_db)
    tables = _table_set(fresh_db)

    for new_name in NEW_TABLES:
        assert new_name in tables, f"New table {new_name} missing"


def test_org_functions_table_exists_with_default_data(fresh_db):
    """org_functions 表存在 + 默认 administrative 主职能数据"""
    _run_full_migration_chain(fresh_db)
    conn = sqlite3.connect(str(fresh_db))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert 'org_functions' in tables

        org_count = conn.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
        admin_count = conn.execute(
            "SELECT COUNT(*) FROM org_functions "
            "WHERE function_type='administrative' AND is_primary=1"
        ).fetchone()[0]

        assert admin_count >= org_count, (
            f"Administrative count {admin_count} < org count {org_count}"
        )
    finally:
        conn.close()


def test_orgs_table_has_org_type_and_scope(fresh_db):
    """orgs 表有 org_type / org_scope 列"""
    _run_full_migration_chain(fresh_db)
    conn = sqlite3.connect(str(fresh_db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(orgs)").fetchall()}
        assert 'org_type' in cols
        assert 'org_scope' in cols
    finally:
        conn.close()


def test_data_preserved_no_loss(fresh_db):
    """数据无丢失 (迁移前旧表计数 vs 迁移后新表计数)"""
    conn = sqlite3.connect(str(fresh_db))
    try:
        before = {}
        for old_name, _ in DATA_COMPARISONS:
            # 迁移前旧表必须存在 (若主 DB 已迁移, 本测试针对迁移前状态运行)
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if old_name not in tables:
                pytest.skip(f"{old_name} not present, DB already migrated")
            before[old_name] = conn.execute(
                f"SELECT COUNT(*) FROM {old_name}"
            ).fetchone()[0]
    finally:
        conn.close()

    _run_full_migration_chain(fresh_db)

    conn = sqlite3.connect(str(fresh_db))
    try:
        for old_name, new_name in DATA_COMPARISONS:
            old_count = before[old_name]
            new_count = conn.execute(
                f"SELECT COUNT(*) FROM {new_name}"
            ).fetchone()[0]
            assert old_count == new_count, (
                f"{old_name}={old_count} vs {new_name}={new_count}"
            )
    finally:
        conn.close()
