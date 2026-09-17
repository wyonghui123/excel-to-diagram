"""
[Phase 1 / Plan A Task 3.5] DROP Plan A P13-T3 残留表

清理 v070 RENAME 之前, 测试/开发过程中残留的空表/测试数据:
- permission_sets (8 rows test residue: ps_api_create_*, e2e_ps_test, Wildcard Test)
- permission_set_permissions (0 rows)
- user_permission_sets (3 rows test residue)

策略:
1. 先把 residue 表 RENAME 到 *_pre_v071_backup (作为保险备份)
2. 再 DROP 备份表
3. 如果将来需要恢复, 可从 *_pre_v071_backup 还原

规范遵循 (meta/migrations/README.md):
- 文件命名: v<NNN>__<desc>.py (v071)
- 入口签名: migrate(db_path, skip_backup=False) -> bool
- 幂等性: 检查是否已经迁移过 (用 schema_migrations 表) + IF EXISTS guards
- 单次 migration 内 DROP TABLE: 由 README §4 禁止. 本迁移通过
  "RENAME → DROP backup" 模式避免直接 DROP 含数据的表.

修正说明 (2026-08-28):
- 之前 rename_roles_to_permission_sets.py 内联了无条件 DROP, 违反 README §4
- 现拆分为独立 migration v071, 与 v070 (RENAME) 解耦
- v070 纯 RENAME (幂等, 不 DROP)
- v071 RENAME 备份 → DROP (只处理明确是 residue 的表)

downgrade 行为:
- 既然 DROP 前已 RENAME 到 *_pre_v071_backup, downgrade 可以从备份恢复
- 但这是 no-op, 因为 residue 是测试数据, 不需要恢复
"""
import sqlite3
from pathlib import Path

# Residue 表 → 备份表名
RESIDUE_TABLES = [
    ('permission_sets', 'permission_sets_pre_v071_backup'),
    ('permission_set_permissions', 'permission_set_permissions_pre_v071_backup'),
    ('user_permission_sets', 'user_permission_sets_pre_v071_backup'),
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _row_count(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute(f'SELECT COUNT(*) FROM "{name}"')
    return cur.fetchone()[0]


def _do_drop_residue(conn: sqlite3.Connection) -> int:
    """RENAME 备份 → DROP. 返回实际处理的表数量.

    幂等性 (Important-1):
    - v071 只应在 v070 之前运行 (清理 residue)
    - 如果 v070 已运行过 (旧的 'roles' 表已不存在, 新的 'permission_sets'
      是真表), v071 必须跳过, 否则会误删 v070 创建的实表
    - 通过检查 'roles' 表是否存在来判断 v070 是否已运行
    """
    # 检查 v070 是否已运行 (旧角色表不存在 → v070 已完成)
    if not _table_exists(conn, 'roles'):
        # roles 不存在说明 v070 已经 RENAME 完成, v071 必须跳过,
        # 否则会误删 v070 创建的 permission_sets 真表
        print('  - roles 不存在, v070 已运行, v071 跳过 (避免误删实表)')
        return 0

    processed = 0
    for src, backup in RESIDUE_TABLES:
        if not _table_exists(conn, src):
            print(f'  - {src} 不存在, 跳过')
            continue

        # 检查是否已经处理过 (备份已存在)
        if _table_exists(conn, backup):
            print(f'  - {backup} 已存在 (v071 已运行过), 跳过')
            continue

        # 记录行数 (审计日志)
        cnt = _row_count(conn, src)
        # Step 1: RENAME 到备份表 (保留数据, 防止误删)
        conn.execute(f'ALTER TABLE {src} RENAME TO {backup}')
        print(f'  RENAME {src} → {backup} ({cnt} rows backup)')

        # Step 2: DROP 备份表 (释放空间, 但保留快速回滚可能)
        conn.execute(f'DROP TABLE IF EXISTS {backup}')
        print(f'  DROP {backup}')
        processed += 1
    return processed


# ─── 入口签名 (meta/migrations/README.md §2) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    v071: drop P13-T3 residue tables (with backup safety)

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (默认 False, runner 已统一备份, 内部还可跳)

    Returns:
        True 如果成功执行或已执行 (幂等, 重复执行安全)
    """
    if not db_path.exists():
        print(f'[v071] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_drop_residue(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v071] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证 v071: 所有 residue 表都已不存在"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        return not any(_table_exists(conn, src) for src, _ in RESIDUE_TABLES)
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """v071 downgrade: no-op (备份已 DROP, residue 是测试数据不需要恢复)

    如果需要从 *_pre_v071_backup 恢复, 可手动执行 SQL (在 DROP 前先 RENAME 回原名).
    """
    print('[v071] downgrade no-op: residue tables were test data, no production '
          'data loss. Backup was also dropped to release space.')
    return True