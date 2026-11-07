# -*- coding: utf-8 -*-
"""[v231] work_order 放开 MTS（按库存生产）+ 产出物料 / 计划数量落库

依据:
  docs/specs/bo-metadata-gap-2026-11-06/tasks.md T9.3

设计:
  · `work_orders` 增 2 列：
      - `item_id`（INTEGER NULL）：生产产出物料（manual 建单必填，
        有来源时由需求来源自动回填）；
      - `planned_qty`（REAL NULL）：计划生产数量，供组件展开与工单追溯。
  · 放宽 `order_id` / `order_line_id` 的 NOT NULL：MTS 手工备货无上游单据，
    项目任务来源的工单亦不冗余订单 / 订单行；服务建单路径行为不变。
  · SQLite 不支持就地放宽 NOT NULL，因此幂等重建 work_orders（同 v163）：
    以 sqlite_master 现有建表 SQL 为准，把两列 NOT NULL 改为 NULL，
    `INSERT ... SELECT` 保数据 → DROP → RENAME → 重建原索引；
    重建期间临时切 `legacy_alter_table` 规避历史失效视图重解析报错。
  · 兜底索引 `idx_work_order_source_demand`（v163 已建则 [SKIP]）。

幂等:
  列先查后加；重建前看 PRAGMA notnull，已可空则 [SKIP]；索引 IF NOT EXISTS。

回滚:
  尽量 DROP 两列（SQLite 不支持时 [KEEP] 保留残留列）。
  NOT NULL 不恢复（存量行可能为 NULL；回滚只删本批次新增物）。

注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。
"""
import re
import sqlite3
import sys
from pathlib import Path

WORK_ORDERS_TABLE = 'work_orders'

#: work_orders 新增列（列名, 列定义）
NEW_COLUMNS = (
    ('item_id', 'INTEGER NULL'),
    ('planned_qty', 'REAL NULL'),
)

#: 需要放宽为 NULL 的既有列（MTS / 项目任务来源无订单、订单行）
REBUILD_COLUMNS = ('order_id', 'order_line_id')

#: 重建时的临时表名
REBUILD_TEMP_TABLE = 'work_orders__v231'

#: 兜底索引（v163 已建）
SOURCE_DEMAND_INDEX = 'idx_work_order_source_demand'
SOURCE_DEMAND_INDEX_SQL = (
    f'CREATE INDEX IF NOT EXISTS {SOURCE_DEMAND_INDEX} '
    f'ON {WORK_ORDERS_TABLE}(source_demand_type, source_demand_id)')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _ensure_column(conn: sqlite3.Connection, table: str, name: str,
                   definition: str) -> None:
    if name in _columns(conn, table):
        print(f'  - [SKIP] 列 {table}.{name} 已存在')
        return
    conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    print(f'  - [ADD] 列 {table}.{name}')


def _notnull(conn: sqlite3.Connection, table: str, column: str):
    """返回列的 NOT NULL 标记；列不存在返回 None。"""
    for row in conn.execute(f'PRAGMA table_info({table})').fetchall():
        if row[1] == column:
            return int(row[3]) != 0
    return None


def _relax_notnull(conn: sqlite3.Connection) -> None:
    """SQLite 不能就地放宽 NOT NULL → 幂等重建 work_orders（保数据 + 保索引）。"""
    columns = [row[1] for row in
               conn.execute(f'PRAGMA table_info({WORK_ORDERS_TABLE})').fetchall()]
    pending = [c for c in REBUILD_COLUMNS
               if c in columns and _notnull(conn, WORK_ORDERS_TABLE, c)]
    if not pending:
        print(f'  - [SKIP] work_orders 的 {" / ".join(REBUILD_COLUMNS)} 已可空，无需重建')
        return

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (WORK_ORDERS_TABLE,)).fetchone()
    ddl = (row[0] if row else '') or ''
    if not ddl.strip():
        print('  - [FAIL] 读不到 work_orders 建表 SQL，跳过重建')
        return

    new_ddl = re.sub(r'CREATE\s+TABLE\s+work_orders',
                     f'CREATE TABLE {REBUILD_TEMP_TABLE}', ddl, count=1,
                     flags=re.IGNORECASE)
    for column in pending:
        new_ddl = re.sub(
            r'(\b%s\s+[A-Za-z0-9_()]+\s+)NOT\s+NULL' % column,
            r'\1NULL', new_ddl, flags=re.IGNORECASE)

    index_sqls = [sql for _name, sql in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' "
        "AND tbl_name=? AND sql IS NOT NULL", (WORK_ORDERS_TABLE,))]

    conn.commit()
    prev_legacy = conn.execute('PRAGMA legacy_alter_table').fetchone()[0]
    conn.execute('PRAGMA legacy_alter_table = ON')
    try:
        conn.execute(f'DROP TABLE IF EXISTS {REBUILD_TEMP_TABLE}')
        conn.execute(new_ddl)
        column_list = ', '.join(columns)
        conn.execute(
            f'INSERT INTO {REBUILD_TEMP_TABLE} ({column_list}) '
            f'SELECT {column_list} FROM {WORK_ORDERS_TABLE}')
        conn.execute(f'DROP TABLE {WORK_ORDERS_TABLE}')
        conn.execute(
            f'ALTER TABLE {REBUILD_TEMP_TABLE} RENAME TO {WORK_ORDERS_TABLE}')
        for sql in index_sqls:
            conn.execute(sql)
        conn.commit()
    finally:
        conn.execute('PRAGMA legacy_alter_table = %d' % int(prev_legacy))

    print(f'  - [REBUILD] work_orders 放宽 NOT NULL: {", ".join(pending)} '
          f'（{len(columns)} 列 / {len(index_sqls)} 索引已保留）')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v231] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v231] 开始: work_order 放开 MTS + 产出物料 / 计划数量')

        if not _table_exists(conn, WORK_ORDERS_TABLE):
            conn.rollback()
            print(f'  - [FAIL] 缺依赖表 {WORK_ORDERS_TABLE}（需先执行 v161）')
            return False

        for name, definition in NEW_COLUMNS:
            _ensure_column(conn, WORK_ORDERS_TABLE, name, definition)

        _relax_notnull(conn)

        if _index_exists(conn, SOURCE_DEMAND_INDEX):
            print(f'  - [SKIP] 索引 {SOURCE_DEMAND_INDEX} 已存在')
        else:
            conn.execute(SOURCE_DEMAND_INDEX_SQL)
            print(f'  - [ADD] 索引 {SOURCE_DEMAND_INDEX}')

        conn.commit()
        print('[v231] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v231] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v231 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, WORK_ORDERS_TABLE):
            print('[v231 verify] FAIL: 缺表 %s' % WORK_ORDERS_TABLE)
            ok = False
        else:
            have = _columns(conn, WORK_ORDERS_TABLE)
            for name, _definition in NEW_COLUMNS:
                if name not in have:
                    print('[v231 verify] FAIL: 缺列 %s.%s'
                          % (WORK_ORDERS_TABLE, name))
                    ok = False
            for column in REBUILD_COLUMNS:
                if column in have and _notnull(conn, WORK_ORDERS_TABLE, column):
                    print('[v231 verify] FAIL: 列 %s.%s 仍 NOT NULL'
                          % (WORK_ORDERS_TABLE, column))
                    ok = False

        if not _index_exists(conn, SOURCE_DEMAND_INDEX):
            print('[v231 verify] FAIL: 缺索引 %s' % SOURCE_DEMAND_INDEX)
            ok = False

        print('[v231 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v231 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v231 rollback] 开始回滚')
        for name, _definition in reversed(NEW_COLUMNS):
            if name not in _columns(conn, WORK_ORDERS_TABLE):
                print(f'  - [SKIP] 列 {WORK_ORDERS_TABLE}.{name} 不存在')
                continue
            try:
                conn.execute(
                    f'ALTER TABLE {WORK_ORDERS_TABLE} DROP COLUMN {name}')
                print(f'  - [DROP] 列 {WORK_ORDERS_TABLE}.{name}')
            except sqlite3.OperationalError:
                print(f'  - [KEEP] 列 {WORK_ORDERS_TABLE}.{name} '
                      f'无法删除（SQLite 限制），保留残留列')

        conn.commit()
        print('[v231 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v231 rollback] 失败: %s' % e)
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