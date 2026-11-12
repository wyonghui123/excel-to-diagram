# -*- coding: utf-8 -*-
"""[v208 2026-11-04] 工单项目任务轴（G15 ETO P1-2）

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.2

范围:
  1. work_orders 新增 project_task_id（INTEGER NULL）：
       非空时必须同时有 project_id；任务需属于同一项目且为活动任务（服务层守卫 G1-G3）。
  2. 新增索引 idx_work_order_project_task(project_id, project_task_id)。
  3. 不改权限 / 菜单 / 参数。

口径:
  · project_task_id 只是执行粒度引用，不复制项目或任务字段，不承担成本。
  · 存量工单保持 NULL（仅归集到 project_id），不猜测历史任务。

幂等:
  先查 pragma table_info / sqlite_master 后加列、建索引；重复执行打印 [SKIP]。

回滚:
  仅当无任何非空 project_task_id 时允许 DROP COLUMN；否则保留列，避免丢失任务归属事实。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v208__work_order_project_task'

TABLE = 'work_orders'
COLUMN = 'project_task_id'
INDEX = 'idx_work_order_project_task'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    return any(row[1] == column for row in rows)


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE):
        print('  - [SKIP] %s 不存在' % TABLE)
        return
    if _column_exists(conn, TABLE, COLUMN):
        print('  - [SKIP] %s.%s 已存在' % (TABLE, COLUMN))
    else:
        conn.execute('ALTER TABLE %s ADD COLUMN %s INTEGER' % (TABLE, COLUMN))
        print('  - [ADD] %s.%s INTEGER' % (TABLE, COLUMN))
    if _index_exists(conn, INDEX):
        print('  - [SKIP] 索引 %s 已存在' % INDEX)
        return
    conn.execute(
        'CREATE INDEX IF NOT EXISTS %s ON %s(project_id, %s)'
        % (INDEX, TABLE, COLUMN))
    print('  - [IDX] %s(project_id, %s)' % (INDEX, COLUMN))


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE):
        print('  - [SKIP] %s 不存在' % TABLE)
        return
    if _index_exists(conn, INDEX):
        conn.execute('DROP INDEX IF EXISTS %s' % INDEX)
        print('  - [DEL] 索引 %s' % INDEX)
    if not _column_exists(conn, TABLE, COLUMN):
        print('  - [SKIP] %s.%s 不存在' % (TABLE, COLUMN))
        return
    used = conn.execute(
        'SELECT 1 FROM %s WHERE %s IS NOT NULL LIMIT 1' % (TABLE, COLUMN)
    ).fetchone()
    if used:
        print('  - [SKIP] %s.%s 已有任务归属数据，保留列' % (TABLE, COLUMN))
        return
    conn.execute('ALTER TABLE %s DROP COLUMN %s' % (TABLE, COLUMN))
    print('  - [DEL] %s.%s' % (TABLE, COLUMN))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v208] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v208] 开始: 工单项目任务轴（G15 ETO）')
        _do_upgrade(conn)
        conn.commit()
        print('[v208] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v208] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v208 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, TABLE):
            print('[v208 verify] FAIL: 缺表 %s' % TABLE)
            return False
        if not _column_exists(conn, TABLE, COLUMN):
            print('[v208 verify] FAIL: 缺列 %s.%s' % (TABLE, COLUMN))
            return False
        if not _index_exists(conn, INDEX):
            print('[v208 verify] FAIL: 缺索引 %s' % INDEX)
            return False
        bad = conn.execute(
            "SELECT COUNT(*) FROM %s "
            "WHERE %s IS NOT NULL AND project_id IS NULL" % (TABLE, COLUMN)
        ).fetchone()[0]
        if bad:
            print('[v208 verify] FAIL: %s 条工单有任务但无项目（违反 G1）' % bad)
            return False
        print('[v208 verify] PASS')
        return True
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(migrate(Path(sys.argv[1]), skip_backup=True))
        print(verify(Path(sys.argv[1])))
