# -*- coding: utf-8 -*-
"""[v163] 生产工单需求追溯 + 工单组件表

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md
  §10.15 作业层统一契约 / §10.16 生产 → 出库 → 发运对象链
  docs/superpowers/specs/2026-10-29-so-wave3/tasks.md T4.3

设计:
  · `work_orders` 增 2 列：`source_demand_type`（sales_order_schedule /
    sales_order_line）+ `source_demand_id`，承载 production 工单的需求追溯
    （service 工单留空，R-ST-0 收窄为 service 专属）。
  · 新建 `work_order_components`（由 work_order_component.yaml 声明，sync_schema
    生成；本迁移做「兜底 CREATE + 兜底索引」）。
  · 索引：`idx_work_order_source_demand`（计划行 → 生产工单 1:N 反查）、
    `idx_work_order_component_work_order` / `idx_work_order_component_item`。
  · SQLite 不支持就地放宽 NOT NULL，因此 **幂等重建 work_orders**：
    以 sqlite_master 的现有建表 SQL 为准，把 `schedule_id` / `severity`
    的 NOT NULL 改为 NULL（生产工单无计划行挂载、无 SLA 严重度），
    `INSERT ... SELECT` 保数据 → DROP 旧表 → RENAME → 重建原索引。
    `created_by/updated_by` 等 sync_schema 增列一并保留。

幂等:
  列 / 表 / 索引先查后用；重建前先看 PRAGMA notnull，已可空则 [SKIP]；
  重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删索引 → 删组件表 → 尽量 DROP COLUMN 两列（不支持时 [KEEP] 保留残留列）。
  NOT NULL 不恢复（存量行可能存在 NULL；回滚只删批次 4a 新增物）。
"""
import re
import sqlite3
import sys
from pathlib import Path

WORK_ORDERS_TABLE = 'work_orders'
COMPONENTS_TABLE = 'work_order_components'

#: work_orders 新增列（列名, 列定义）
NEW_COLUMNS = (
    ('source_demand_type', 'TEXT NULL'),
    ('source_demand_id', 'INTEGER NULL'),
)

#: 需要放宽为 NULL 的既有列（生产工单：无计划行挂载、无 SLA 严重度）
REBUILD_COLUMNS = ('schedule_id', 'severity')

#: 重建时的临时表名
REBUILD_TEMP_TABLE = 'work_orders__v163'

COMPONENTS_DDL = """
CREATE TABLE IF NOT EXISTS work_order_components (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id      INTEGER NOT NULL,
    structure_id       INTEGER NULL,
    structure_line_id  INTEGER NULL,
    component_item_id  INTEGER NOT NULL,
    line_no            INTEGER NULL,
    qty_per            REAL NULL,
    fixed_qty          REAL NULL,
    scrap_rate         REAL NULL,
    qty_required       REAL NULL,
    optional_flag      INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

INDEXES = (
    ('idx_work_order_source_demand',
     f'CREATE INDEX IF NOT EXISTS idx_work_order_source_demand '
     f'ON {WORK_ORDERS_TABLE}(source_demand_type, source_demand_id)'),
    ('idx_work_order_component_work_order',
     f'CREATE INDEX IF NOT EXISTS idx_work_order_component_work_order '
     f'ON {COMPONENTS_TABLE}(work_order_id)'),
    ('idx_work_order_component_item',
     f'CREATE INDEX IF NOT EXISTS idx_work_order_component_item '
     f'ON {COMPONENTS_TABLE}(component_item_id)'),
)


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
    """SQLite 不能就地放宽 NOT NULL → 幂等重建 work_orders（保数据 + 保索引）。

    注意：SQLite 3.25+ 的 ALTER TABLE RENAME 会重解析全部视图，本库存在
    3 个历史遗留的失效视图（org_legal_entity / org_sales_org / party_internal，
    引用不存在的 org_functions），重解析会直接报错。故重建期间临时切到
    `legacy_alter_table`（纯改名，不重解析视图），结束后恢复原值。
    """
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
        print(f'[v163] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v163] 开始: 生产工单需求追溯 + 工单组件表')

        if not _table_exists(conn, WORK_ORDERS_TABLE):
            conn.rollback()
            print(f'  - [FAIL] 缺依赖表 {WORK_ORDERS_TABLE}（需先执行 v161）')
            return False

        for name, definition in NEW_COLUMNS:
            _ensure_column(conn, WORK_ORDERS_TABLE, name, definition)

        _relax_notnull(conn)

        if _table_exists(conn, COMPONENTS_TABLE):
            print(f'  - [SKIP] 表 {COMPONENTS_TABLE} 已存在')
        else:
            conn.execute(COMPONENTS_DDL)
            print(f'  - [CREATE] 表 {COMPONENTS_TABLE}')

        for name, sql in INDEXES:
            if _index_exists(conn, name):
                print(f'  - [SKIP] 索引 {name} 已存在')
            else:
                conn.execute(sql)
                print(f'  - [ADD] 索引 {name}')

        conn.commit()
        print('[v163] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v163] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v163 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, WORK_ORDERS_TABLE):
            print('[v163 verify] FAIL: 缺表 %s' % WORK_ORDERS_TABLE)
            ok = False
        else:
            have = _columns(conn, WORK_ORDERS_TABLE)
            for name, _definition in NEW_COLUMNS:
                if name not in have:
                    print('[v163 verify] FAIL: 缺列 %s.%s'
                          % (WORK_ORDERS_TABLE, name))
                    ok = False
            for column in REBUILD_COLUMNS:
                if column in have and _notnull(conn, WORK_ORDERS_TABLE, column):
                    print('[v163 verify] FAIL: 列 %s.%s 仍 NOT NULL'
                          % (WORK_ORDERS_TABLE, column))
                    ok = False

        if not _table_exists(conn, COMPONENTS_TABLE):
            print('[v163 verify] FAIL: 缺表 %s' % COMPONENTS_TABLE)
            ok = False
        else:
            required = ('work_order_id', 'structure_id', 'structure_line_id',
                        'component_item_id', 'line_no', 'qty_per', 'fixed_qty',
                        'scrap_rate', 'qty_required', 'optional_flag')
            have = _columns(conn, COMPONENTS_TABLE)
            for column in required:
                if column not in have:
                    print('[v163 verify] FAIL: 缺列 %s.%s'
                          % (COMPONENTS_TABLE, column))
                    ok = False

        for name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v163 verify] FAIL: 缺索引 %s' % name)
                ok = False

        print('[v163 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v163 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v163 rollback] 开始回滚')
        for name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX {name}')
                print(f'  - [DROP] 索引 {name}')
            else:
                print(f'  - [SKIP] 索引 {name} 不存在')

        if _table_exists(conn, COMPONENTS_TABLE):
            conn.execute(f'DROP TABLE {COMPONENTS_TABLE}')
            print(f'  - [DROP] 表 {COMPONENTS_TABLE}')
        else:
            print(f'  - [SKIP] 表 {COMPONENTS_TABLE} 不存在')

        for name, _definition in reversed(NEW_COLUMNS):
            if name not in _columns(conn, WORK_ORDERS_TABLE):
                print(f'  - [SKIP] 列 {WORK_ORDERS_TABLE}.{name} 不存在')
                continue
            try:
                conn.execute(f'ALTER TABLE {WORK_ORDERS_TABLE} DROP COLUMN {name}')
                print(f'  - [DROP] 列 {WORK_ORDERS_TABLE}.{name}')
            except sqlite3.OperationalError:
                print(f'  - [KEEP] 列 {WORK_ORDERS_TABLE}.{name} 无法删除（SQLite 限制），保留残留列')

        conn.commit()
        print('[v163 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v163 rollback] 失败: %s' % e)
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
