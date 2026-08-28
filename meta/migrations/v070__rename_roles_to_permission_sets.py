"""
[Phase 1 / Plan A Task 3] 7 张 role 相关表 RENAME 为 permission_set 相关表

旧表 → 新表映射:
- roles → permission_sets
- role_permissions → permission_set_permissions
- role_data_permissions → permission_set_data_permissions
- role_dimension_scopes → permission_set_dimension_scopes
- role_menu_permissions → permission_set_menu_permissions
- user_roles → user_permission_sets

规范遵循 (meta/migrations/README.md):
- 文件命名: v<NNN>__<desc>.py (v070)
- 入口签名: migrate(db_path, skip_backup=False) -> bool
- 幂等性: 每个 RENAME 前检查 new_name 是否已存在, 避免重复执行破坏数据
- DROP residue 表: 由独立 migration v071 处理 (本文件纯 RENAME)

修正说明 (2026-08-28, 当前 DB 状态):
- 旧 plan 中 `role_menus` / `role_effective_intents` 不存在, 已用真实表名 `role_menu_permissions`
  并跳过 `role_effective_intents`
- 当前 DB 已有 test residue: `permission_sets` (8), `permission_set_permissions` (0),
  `user_permission_sets` (3) → 由 v071__drop_p13_t3_residue_tables.py 单独 DROP
- `role_intents` (1 row) 和 `roles_v1_backup` (1 row) 不在 spec 范围, 保持原样
"""
import sqlite3
from pathlib import Path

# RENAME 顺序: 仅含真实存在的旧表
RENAME_PAIRS = [
    ('roles', 'permission_sets'),
    ('role_permissions', 'permission_set_permissions'),
    ('role_data_permissions', 'permission_set_data_permissions'),
    ('role_dimension_scopes', 'permission_set_dimension_scopes'),
    ('role_menu_permissions', 'permission_set_menu_permissions'),
    ('user_roles', 'user_permission_sets'),
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> None:
    """执行 rename (幂等: 已存在的 new_name 跳过, 不抛错)"""
    for old_name, new_name in RENAME_PAIRS:
        # 守卫 1: 旧表不存在 → 跳过 (DB 不含该表, 无需 rename)
        if not _table_exists(conn, old_name):
            print(f'  - {old_name} 不存在, 跳过 RENAME')
            continue
        # 守卫 2: 新表已存在 → 跳过 (已是终态, 重复执行无害)
        if _table_exists(conn, new_name):
            print(f'  - {new_name} 已存在, 跳过 RENAME {old_name} → {new_name}')
            continue
        conn.execute(f'ALTER TABLE {old_name} RENAME TO {new_name}')
        print(f'  RENAME {old_name} → {new_name}')


def _do_downgrade(conn: sqlite3.Connection) -> None:
    """回滚 (逆序)"""
    for old_name, new_name in reversed(RENAME_PAIRS):
        if not _table_exists(conn, new_name):
            print(f'  - {new_name} 不存在, 跳过反向 RENAME')
            continue
        if _table_exists(conn, old_name):
            print(f'  - {old_name} 已存在, 跳过反向 RENAME {new_name} → {old_name}')
            continue
        conn.execute(f'ALTER TABLE {new_name} RENAME TO {old_name}')
        print(f'  RENAME {new_name} → {old_name}')


# ─── 入口签名 (meta/migrations/README.md §2) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    v070: rename roles → permission_sets

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (runner 已统一备份, 内部可跳过)

    Returns:
        True 如果成功执行或已执行 (幂等)
    """
    if not db_path.exists():
        print(f'[v070] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v070] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证 migration 是否已正确执行 (permission_set_* 表存在)"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        new_tables = [new for _, new in RENAME_PAIRS]
        for t in new_tables:
            if not _table_exists(conn, t):
                return False
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """回滚 v070 (反向 RENAME)

    注意: 不重建 v071 已 DROP 的 residue 表, 因为它们本来就是空表,
    无数据需要恢复. 详见 v071__drop_p13_t3_residue_tables.py docstring.
    """
    if not db_path.exists():
        print(f'[v070] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_downgrade(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v070] downgrade 失败: {e}')
        raise
    finally:
        conn.close()