# -*- coding: utf-8 -*-
"""v165 冻结 task_executions 残余行（账本统一 Phase 2a）

背景
  v158 已把 completed/failed 等已完结行归档到 `task_execution_archive`，
  源表只剩 pending 3304 / running 1（实测）。这些行没有任何生产者（Gen1
  调度器已无 cron 循环、无 handler 注册），永远等不到执行 —— 留着会让
  「账本统一」永远无法判定清零。

  PM 拍板（2026-10-31）：把 pending/running 标为 `cancelled`，然后执行统一
  （跨库投影到 `task_events`，最后 v166 物理退役）。

本迁移做什么
  1. 把 `task_executions` 中 status IN ('pending','running') 的行置为
     `cancelled`；
  2. `completed_at` 写当前时间，`error_message` 写退役原因标记
     （`GEN1_LEDGER_FROZEN`）—— 便于审计与回滚识别；
  3. 只改状态，不删行：行留给 Phase 2b 跨库投影工具
     `meta/tools/task_execution_ledger_migrate.py`，最后由 v166 清表。

幂等
  - 只更新 pending/running 行；二次执行更新 0 行，不报错。

回滚（rollback = downgrade）
  - 把带 `GEN1_LEDGER_FROZEN` 标记的 cancelled 行改回 `pending` 并清空
    `completed_at` / `error_message`。
  - 局限：原 `running` 无法与 `pending` 区分（状态列已被覆盖），回滚统一
    恢复为 pending。
"""
import sqlite3
import sys
from pathlib import Path

TABLE = 'task_executions'
FROZEN_STATUSES = ('pending', 'running')
FROZEN_MARKER = 'GEN1_LEDGER_FROZEN'
REASON = (FROZEN_MARKER + ': Gen1 执行账本已无生产者，'
          'pending/running 行冻结为 cancelled（v165），待投影后退役（v166）')

_STATUS_SQL = 'status IN (' + ', '.join(f"'{s}'" for s in FROZEN_STATUSES) + ')'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v165] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v165] {TABLE} 不存在，已退役/从未建过，跳过')
            return True

        before = _count(conn, f"SELECT COUNT(*) FROM \"{TABLE}\" WHERE {_STATUS_SQL}")
        if before == 0:
            print(f'[v165] 无 pending/running 行，跳过（幂等）')
            return True

        has_completed = _column_exists(conn, TABLE, 'completed_at')
        has_error = _column_exists(conn, TABLE, 'error_message')
        if not (has_completed and has_error):
            raise RuntimeError(
                f'{TABLE} 缺 completed_at / error_message 列，无法记录冻结标记')

        print(f'[v165] 冻结 {TABLE} 残余行（pending/running → cancelled）')
        conn.execute('BEGIN')
        conn.execute(
            f'UPDATE "{TABLE}" SET status = \'cancelled\', '
            f'completed_at = COALESCE(completed_at, datetime(\'now\')), '
            f'error_message = ? WHERE {_STATUS_SQL}',
            (REASON,),
        )
        after = _count(conn, f"SELECT COUNT(*) FROM \"{TABLE}\" WHERE {_STATUS_SQL}")
        conn.commit()
        print(f'  冻结行数: {before}，剩余 pending/running: {after}')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v165] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v165 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v165 verify] OK: {TABLE} 已不存在（已退役）')
            return True
        leftovers = _count(conn, f"SELECT COUNT(*) FROM \"{TABLE}\" WHERE {_STATUS_SQL}")
        if leftovers:
            print(f'[v165 verify] FAIL: 仍有 {leftovers} 行 pending/running')
            return False
        print(f'[v165 verify] OK: 无 pending/running 残留')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """带冻结标记的 cancelled 行恢复为 pending（running 不可区分）。"""
    if not db_path.exists():
        print(f'[v165] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v165] rollback: {TABLE} 不存在，无需回滚')
            return True
        marker_sql = 'error_message LIKE ?'
        marker_param = '%' + FROZEN_MARKER + '%'
        restored = _count(
            conn,
            f"SELECT COUNT(*) FROM \"{TABLE}\" WHERE status = 'cancelled' AND {marker_sql}",
            (marker_param,),
        )
        if restored == 0:
            print('[v165] rollback: 无冻结标记行，跳过')
            return True
        conn.execute('BEGIN')
        conn.execute(
            f'UPDATE "{TABLE}" SET status = \'pending\', completed_at = NULL, '
            f'error_message = NULL WHERE status = \'cancelled\' AND {marker_sql}',
            (marker_param,),
        )
        conn.commit()
        print(f'  回滚行数: {restored}（统一恢复为 pending）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v165] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v165] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v165] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v165] verify: {"PASS" if _v else "FAIL"}')
