# -*- coding: utf-8 -*-
"""v166 退役 Gen1 执行账本表（账本统一 Phase 2c）

[ALLOW_DESTRUCTIVE] 本迁移物理删除 `task_executions` / `task_execution_archive`
两张运行账本表（数据已由投影工具转存到 Gen2 `task_events`）。

前置（缺一不可）
  1. v158：把已完成行归档到 `task_execution_archive`；
  2. v165：把 pending/running 残余行冻结为 cancelled；
  3. `python -m meta.tools.task_execution_ledger_migrate`
     --app-db <应用库> --platform-db <平台库>
     把两张账本的行投影为 `task_events`（event_type=`legacy_execution`）。

破坏性守卫
  - 源表仍有行时，必须显式设置环境变量
    `ALLOW_TASK_LEDGER_DROP_WITH_ROWS=1` 才允许删除；否则本迁移返回 False
    （记 FAILED、保留表），避免「没投影就删账本」的数据丢失。
  - 删除沿用 v155 的 `RENAME → DROP backup` 模式，不做裸 DROP。

幂等
  - 两张表都不存在 → 直接返回 True。

回滚（rollback = downgrade）
  - 只重建空的 `task_executions`（结构照 `meta/core/task_infra_schema.py`）；
    数据不回滚（已在 `task_events` 账上，archive 结构由 v158 可重建）。
"""
import os
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from meta.core.task_infra_schema import TASK_EXECUTION_DDL  # noqa: E402

TABLES = ('task_executions', 'task_execution_archive')
BACKUP_SUFFIX = '_pre_v166_backup'
ALLOW_ENV = 'ALLOW_TASK_LEDGER_DROP_WITH_ROWS'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def _allow_drop_with_rows() -> bool:
    return os.environ.get(ALLOW_ENV, '').strip().lower() in ('1', 'true', 'yes', 'on')


def prerequisites() -> list:
    return [
        'v158__archive_task_executions.py',
        'v165__freeze_task_executions.py',
    ]


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v166] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        existing = [t for t in TABLES if _table_exists(conn, t)]
        if not existing:
            print('[v166] task_executions / task_execution_archive 均不存在，已退役，跳过')
            return True

        counts = {t: _row_count(conn, t) for t in existing}
        total = sum(counts.values())
        if total > 0 and not _allow_drop_with_rows():
            print(f'[v166] 拒绝删除：账本仍有 {total} 行 {counts}')
            print(f'       请先跑投影工具，确认后设置 {ALLOW_ENV}=1 再重跑')
            return False

        print('[v166] 退役 Gen1 执行账本表')
        conn.execute('BEGIN')
        for table in existing:
            backup = table + BACKUP_SUFFIX
            conn.execute(f'ALTER TABLE "{table}" RENAME TO "{backup}"')
            conn.execute(f'DROP TABLE IF EXISTS "{backup}"')
            print(f'  RENAME+DROP {table} → {backup} ({counts[table]} rows)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v166] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v166 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        leftovers = [t for t in TABLES if _table_exists(conn, t)]
        leftovers += [t + BACKUP_SUFFIX for t in TABLES
                      if _table_exists(conn, t + BACKUP_SUFFIX)]
        if leftovers:
            print(f'[v166 verify] FAIL: 旧表仍在: {leftovers}')
            return False
        print('[v166 verify] OK: task_executions / task_execution_archive 已退役')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """只重建空的 task_executions（数据不回滚，已在 task_events）。"""
    if not db_path.exists():
        print(f'[v166] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(TASK_EXECUTION_DDL)
        conn.commit()
        print('  rollback: 重建空表 task_executions')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v166] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v166] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v166] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v166] verify: {"PASS" if _v else "FAIL"}')
