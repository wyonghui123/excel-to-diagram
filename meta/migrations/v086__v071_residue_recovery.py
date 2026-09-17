# -*- coding: utf-8 -*-
"""
[v086 2026-09-12] P0-2 修补 v071 误删实表的 recovery migration

背景 (delta-7 staging 500 事故根因):
  v071 的守卫 "if _table_exists(conn, 'roles'): DROP permission_sets ..."
  假设 roles 存在 = v070 没跑, 但 staging 锚点库处于混合状态
  (roles + permission_sets 同时存在) 时, v071 误把 v070 RENAME 出来的
  permission_sets 实表当作 residue 删掉, 致后端 500.

修复策略:
  本 migration 只在 v071 误删痕迹可见时执行修复 (幂等):
  - 如果 *_pre_v071_backup 表存在 (v071 RENAME 备份步骤的产物),
    且对应的 spec16 实表不存在 (permission_sets/permission_set_permissions/
    user_permission_sets) → 从备份恢复数据 (RENAME 回去)

  注意: 本 migration 不删 *_pre_v071_backup 表 (留给未来类似事故分析).
  不动 *_pre_mx_backup (9-05 复盘产物) 和 *_pre_v079/v083_backup (更晚迁移产物).

幂等性:
  - 实表已存在 → 跳过 (无动作)
  - 备份表不存在 → 跳过 (无法恢复)
  - schema_migrations 不写记录, 避免被工具误跳过
    (v086 是 idempotent recovery, 不需要审计为"已迁移")

downgrade: 不支持 (recovery 类 migration 无逆操作)
"""
import sqlite3
from pathlib import Path


# v071 误删的 3 张实表 → 对应的 v071 RENAME 备份表
RECOVERY_PAIRS = [
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


def _do_recover(conn: sqlite3.Connection) -> int:
    """从 v071 备份恢复 spec16 实表. 返回恢复的表数量."""
    recovered = 0
    for real, backup in RECOVERY_PAIRS:
        # 实表已存在 → 跳过 (幂等)
        if _table_exists(conn, real):
            print(f'  - {real} 已存在, 跳过恢复 (幂等)')
            continue
        # 备份表不存在 → 跳过 (无源)
        if not _table_exists(conn, backup):
            print(f'  - {backup} 不存在, 跳过恢复 (无源)')
            continue
        # RENAME 回去
        try:
            conn.execute(f'ALTER TABLE {backup} RENAME TO {real}')
            print(f'  [v086] RECOVER {backup} -> {real} (v071 误删回滚)')
            recovered += 1
        except Exception as e:
            print(f'  [v086] FAIL recover {real}: {e}')
            raise
    return recovered


# ─── 入口签名 (meta/migrations/README.md §2) ───

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """[v086] v071 误删实表 idempotent recovery

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 由 runner 决定, 本 migration 不需要

    Returns:
        True (recovery 是 idempotent 的, 总是成功; 实际恢复表数 print 出来)
    """
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v086] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v086] 开始: v071 误删实表 idempotent recovery')
        recovered = _do_recover(conn)
        conn.commit()
        print(f'  [v086] summary: recovered={recovered}/{len(RECOVERY_PAIRS)}')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v086] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """验证: 3 张 spec16 实表都存在 (v085 验证风格)"""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        missing = [
            real for real, _ in RECOVERY_PAIRS
            if not _table_exists(conn, real)
        ]
        if missing:
            print(f'  [v086 verify] FAIL: 缺实表: {missing}')
            return False
        return True
    finally:
        conn.close()
