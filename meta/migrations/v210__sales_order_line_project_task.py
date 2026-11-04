# -*- coding: utf-8 -*-
"""[v210 2026-11-04] 销售订单行项目任务轴（G15 ETO P2-1）

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.1
  docs/specs/spec-project-g15-eto-P2-tasks.md 阶段 A

范围:
  1. sales_order_lines 新增 project_task_id（INTEGER NOT NULL DEFAULT 0）：
       非空时必须同时有 project_id（行或抬头归一化后），任务须属于同一项目
       且为活动任务（服务层守卫 R1-R3）。
  2. 新增索引 idx_sales_order_line_project_task(project_task_id)。
  3. 不改权限 / 菜单 / 参数。

口径:
  · 任务只是执行粒度引用；行项目仍以 project_id 归集，不复制项目字段。
  · 0 为「未挂任务」哨兵（与库存段列一致），存量行保持 0。

幂等:
  先查 pragma table_info / sqlite_master 后加列、建索引；重复执行打印 [SKIP]。

回滚:
  [ALLOW_DESTRUCTIVE] 仅删索引；列不删除（SQLite 无安全 DROP COLUMN，且历史任务归属不可丢）。
"""
import sqlite3
import sys
from pathlib import Path

MIGRATION_NAME = 'v210__sales_order_line_project_task'

TABLE = 'sales_order_lines'
COLUMN = 'project_task_id'
INDEX = 'idx_sales_order_line_project_task'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    return any(row[1] == column for row in rows)


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE):
        print('  - [SKIP] 表 %s 不存在' % TABLE)
        return
    if _column_exists(conn, TABLE, COLUMN):
        print('  - [SKIP] %s.%s 已存在' % (TABLE, COLUMN))
    else:
        conn.execute(
            'ALTER TABLE %s ADD COLUMN %s INTEGER NOT NULL DEFAULT 0'
            % (TABLE, COLUMN))
        print('  - [ADD] %s.%s INTEGER NOT NULL DEFAULT 0' % (TABLE, COLUMN))
    if _index_exists(conn, INDEX):
        print('  - [SKIP] 索引 %s 已存在' % INDEX)
    else:
        conn.execute('CREATE INDEX IF NOT EXISTS %s ON %s(%s)'
                     % (INDEX, TABLE, COLUMN))
        print('  - [ADD] 索引 %s' % INDEX)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v210] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v210] 开始: 销售订单行项目任务轴（G15 P2-1）')
        _do_upgrade(conn)
        conn.commit()
        print('[v210] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v210] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v210 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, TABLE):
            print('[v210 verify] FAIL: 缺表 %s' % TABLE)
            ok = False
        else:
            if not _column_exists(conn, TABLE, COLUMN):
                print('[v210 verify] FAIL: 缺列 %s.%s' % (TABLE, COLUMN))
                ok = False
            if not _index_exists(conn, INDEX):
                print('[v210 verify] FAIL: 缺索引 %s' % INDEX)
                ok = False
        print('[v210 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v210 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _index_exists(conn, INDEX):
            conn.execute('DROP INDEX IF EXISTS %s' % INDEX)
            print('  - [DROP] 索引 %s' % INDEX)
        conn.commit()
        print('[v210 rollback] 完成（列保留，SQLite 无安全 DROP COLUMN）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v210 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)

