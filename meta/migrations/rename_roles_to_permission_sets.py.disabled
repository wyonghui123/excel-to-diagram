"""
[Phase 1] 7 张 role 相关表 RENAME 为 permission_set 相关表

旧表 → 新表映射:
- roles → permission_sets
- role_permissions → permission_set_permissions
- role_data_permissions → permission_set_data_permissions
- role_dimension_scopes → permission_set_dimension_scopes
- role_menu_permissions → permission_set_menu_permissions
- user_roles → user_permission_sets

修正说明 (2026-08-28, 当前 DB 状态):
- 旧 plan 中 `role_menus` / `role_effective_intents` 不存在, 已用真实表名 `role_menu_permissions`
  并跳过 `role_effective_intents`
- 当前 DB 已有 test residue: `permission_sets` (8), `permission_set_permissions` (0),
  `user_permission_sets` (3) → 先 DROP, 再 RENAME 真实表
- `role_intents` (1 row) 和 `roles_v1_backup` (1 row) 不在 spec 范围, 保持原样
"""
import sqlite3

# DROP 顺序: 先删 test residue (PM 决策: option A, 仅 DROP 空表/residue)
DROP_TABLES = [
    'permission_sets',
    'permission_set_permissions',
    'user_permission_sets',
]

# RENAME 顺序: 仅含真实存在的旧表
RENAME_PAIRS = [
    ('roles', 'permission_sets'),
    ('role_permissions', 'permission_set_permissions'),
    ('role_data_permissions', 'permission_set_data_permissions'),
    ('role_dimension_scopes', 'permission_set_dimension_scopes'),
    ('role_menu_permissions', 'permission_set_menu_permissions'),
    ('user_roles', 'user_permission_sets'),
]


def upgrade(conn: sqlite3.Connection) -> None:
    """执行 drop + rename"""
    # 1. DROP test residue / 空表 (PM 决策: option A)
    for table in DROP_TABLES:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        if cur.fetchone() is None:
            print(f'  - {table} 不存在, 跳过 DROP')
            continue
        conn.execute(f'DROP TABLE IF EXISTS {table}')
        print(f'  ✓ DROP {table}')

    # 2. RENAME 真实表 (跳过不存在的, 不报错)
    for old_name, new_name in RENAME_PAIRS:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (old_name,)
        )
        if cur.fetchone() is None:
            print(f'  - {old_name} 不存在, 跳过 RENAME')
            continue
        conn.execute(f'ALTER TABLE {old_name} RENAME TO {new_name}')
        print(f'  ✓ RENAME {old_name} → {new_name}')

    conn.commit()


def downgrade(conn: sqlite3.Connection) -> None:
    """回滚 (逆序)"""
    # 1. 反向 RENAME
    for old_name, new_name in reversed(RENAME_PAIRS):
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (new_name,)
        )
        if cur.fetchone() is None:
            print(f'  - {new_name} 不存在, 跳过反向 RENAME')
            continue
        conn.execute(f'ALTER TABLE {new_name} RENAME TO {old_name}')
        print(f'  ✓ RENAME {new_name} → {old_name}')

    conn.commit()


def migrate(db_path, skip_backup: bool = False) -> bool:
    """migration_runner 入口规范: migrate(db_path, skip_backup=False) -> bool

    runner (_execute_py_migration) 只认 migrate() 签名,
    缺少时会被静默 SKIP (migration_runner.py:640-644), DB 永不迁移。
    本包装把 runner 传的 db_path 转成 connection 后调 upgrade()。
    """
    conn = sqlite3.connect(str(db_path))
    try:
        upgrade(conn)
    finally:
        conn.close()
    return True
