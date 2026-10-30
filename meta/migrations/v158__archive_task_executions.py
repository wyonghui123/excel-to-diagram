# -*- coding: utf-8 -*-
"""v158 归档 task_executions 已完结行（账本归档 Phase 1）

背景
  `task_executions` 实测 25642 行（completed 22337 / pending 3304 / running 1），
  最后写入 2026-10-14。该表唯一写入路径是 `meta/core/task_scheduler.py` 的
  `_execute_task`（内部调用 queue_manager.submit），而启动后没有 cron 循环、
  也没有 handler 注册 —— 运行时没有生产者，历史 completed 行只增不减。

  本迁移只做「归档」，不改 API、不删表：把非 pending/running 的行搬到
  `task_execution_archive`，源表保留 pending/running 以便将来恢复生产者。

本迁移做什么
  1. 用 PRAGMA table_info(task_executions) 动态克隆 DDL 建
     `task_execution_archive`（列名/类型加引号，不复制默认值），末尾追加
     `archived_at TEXT`；
  2. `INSERT ... SELECT` 归档 status NOT IN ('pending','running') 且尚未归档的行；
  3. 插入后校验新增归档行数 == 源表待归档行数；
  4. `DELETE FROM task_executions WHERE id IN (SELECT id FROM task_execution_archive)`
     只删已归档行；
  5. 全过程单事务，异常 rollback + raise。

幂等
  - `CREATE TABLE IF NOT EXISTS` + `id NOT IN (SELECT id FROM archive)`：
    二次执行新增归档 0 行，不报错。

回滚（rollback = downgrade）
  - 把 archive 行按 id NOT EXISTS 复制回 task_executions（列对齐，排除
    archived_at），成功后 DROP TABLE IF EXISTS task_execution_archive。
"""
import sqlite3
import sys
from pathlib import Path

SOURCE = 'task_executions'
ARCHIVE = 'task_execution_archive'
KEEP_STATUSES = ('pending', 'running')

_KEEP_SQL = 'status NOT IN (' + ', '.join(f"'{s}'" for s in KEEP_STATUSES) + ')'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _source_columns(conn: sqlite3.Connection) -> list:
    """[(列名, 类型), ...]，用于克隆 DDL 与列对齐。"""
    return [(r[1], r[2]) for r in conn.execute(f'PRAGMA table_info("{SOURCE}")').fetchall()]


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _archive_ddl(columns: list) -> str:
    defs = []
    for name, type_name in columns:
        if type_name:
            defs.append(f'{_q(name)} {_q(type_name)}')
        else:
            defs.append(_q(name))
    defs.append(f'{_q("archived_at")} {_q("TEXT")}')
    return f'CREATE TABLE IF NOT EXISTS {_q(ARCHIVE)} (' + ', '.join(defs) + ')'


def _count(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


def _status_counts(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        f'SELECT status, COUNT(*) FROM {_q(SOURCE)} GROUP BY status'
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def migrate(db_path: Path, skip_backup: bool = True) -> bool:
    if not db_path.exists():
        print(f'[v158] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, SOURCE):
            print(f'[v158] {SOURCE} 不存在，已退役/从未建过，跳过')
            return True

        print('[v158] 归档 task_executions 已完结行')
        columns = _source_columns(conn)
        col_refs = ', '.join(_q(n) for n, _t in columns)

        conn.execute('BEGIN')

        conn.execute(_archive_ddl(columns))

        archive_before = _count(conn, f'SELECT COUNT(*) FROM {_q(ARCHIVE)}')
        expected_new = _count(
            conn,
            f'SELECT COUNT(*) FROM {_q(SOURCE)} WHERE {_KEEP_SQL} '
            f'AND id NOT IN (SELECT id FROM {_q(ARCHIVE)})',
        )

        conn.execute(
            f'INSERT INTO {_q(ARCHIVE)} ({col_refs}, {_q("archived_at")}) '
            f'SELECT {col_refs}, datetime(\'now\') FROM {_q(SOURCE)} '
            f'WHERE {_KEEP_SQL} AND id NOT IN (SELECT id FROM {_q(ARCHIVE)})'
        )

        archive_after = _count(conn, f'SELECT COUNT(*) FROM {_q(ARCHIVE)}')
        inserted = archive_after - archive_before
        if inserted != expected_new:
            raise RuntimeError(
                f'归档行数不一致: inserted={inserted} expected={expected_new}'
            )

        conn.execute(
            f'DELETE FROM {_q(SOURCE)} WHERE id IN (SELECT id FROM {_q(ARCHIVE)})'
        )

        counts = _status_counts(conn)
        conn.commit()

        remaining = {s: counts.get(s, 0) for s in KEEP_STATUSES}
        print(f'  归档行数: {inserted}')
        print('  剩余: ' + ', '.join(f'{s}={n}' for s, n in remaining.items()))
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v158] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v158 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, ARCHIVE):
            print(f'[v158 verify] FAIL: {ARCHIVE} 不存在')
            return False
        if not _table_exists(conn, SOURCE):
            print(f'[v158 verify] OK: {SOURCE} 已不存在（仅归档表保留）')
            return True

        counts = _status_counts(conn)
        info = ', '.join(f'{s}={counts.get(s, 0)}' for s in KEEP_STATUSES)
        leftover = _count(conn, f'SELECT COUNT(*) FROM {_q(SOURCE)} WHERE {_KEEP_SQL}')
        if leftover:
            print(f'[v158 verify] FAIL: 源表仍有 {leftover} 行非 pending/running（{info}）')
            return False
        archived = _count(conn, f'SELECT COUNT(*) FROM {_q(ARCHIVE)}')
        print(f'[v158 verify] OK: 可归档残留 0，archive={archived}（{info}）')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """archive 行按 id NOT EXISTS 复制回源表，然后 DROP archive。"""
    if not db_path.exists():
        print(f'[v158] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, ARCHIVE):
            print(f'[v158] rollback: {ARCHIVE} 不存在，无需回滚')
            return True
        if not _table_exists(conn, SOURCE):
            print(f'[v158] rollback FAIL: {SOURCE} 不存在，无法回填（archive 保留）')
            return False

        columns = _source_columns(conn)
        col_refs = ', '.join(_q(n) for n, _t in columns)
        src_cols = ', '.join(f'{_q(ARCHIVE)}.{_q(n)}' for n, _t in columns)

        print('[v158] rollback: archive 回填 task_executions')
        conn.execute('BEGIN')
        conn.execute(
            f'INSERT INTO {_q(SOURCE)} ({col_refs}) '
            f'SELECT {src_cols} FROM {_q(ARCHIVE)} '
            f'WHERE NOT EXISTS (SELECT 1 FROM {_q(SOURCE)} t WHERE t.id = {_q(ARCHIVE)}.id)'
        )
        restored = _count(conn, f'SELECT COUNT(*) FROM {_q(SOURCE)}')
        conn.execute(f'DROP TABLE IF EXISTS {_q(ARCHIVE)}')
        conn.commit()
        print(f'  回填后 {SOURCE} 行数: {restored}，{ARCHIVE} 已删除')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v158] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v158] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v158] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v158] verify: {"PASS" if _v else "FAIL"}')
