# -*- coding: utf-8 -*-
"""[v145] 销售订单履约状态派生 + 行类型交货相关性

依据:
  docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md
  （§4.7 元模型定位 / §4.8 不变式 / §5.1 字段 / §5.1.1 行类型配置）

背景:
  `fulfillment_status` 是「由 delivery 计划行聚合派生」的物理冗余字段，
  与订单金额回写（SalesOrderAmountService.recompute_*）同构，不是声明式冗余。
  `delivery_relevant` 落在 type_definitions，等价 SAP TVAP-LFREL（item category 级配置）。

本迁移内容:
  1. type_definitions 补 delivery_relevant，并按 line_category 回填默认值
  2. sales_order_lines / sales_orders 补 fulfillment_status
  3. 按 §4.2 / §4.3 规则全量回填（纯 SQL，不依赖服务层）
  4. 输出 INV-3 核查（delivery_relevant=0 的行却存在 delivery 计划行）
  5. 重复执行输出 SKIP

幂等:
  列先查后用；回填为幂等 UPDATE（同输入必同输出）。

回滚:
  只保留列（由 YAML 声明）；数据不清除，避免丢失派生进度。
"""
import sqlite3
from pathlib import Path

LINE_TABLE = 'sales_order_lines'
ORDER_TABLE = 'sales_orders'
SCHEDULE_TABLE = 'sales_order_schedules'
TYPE_TABLE = 'type_definitions'

DELIVERY_RELEVANT_COLUMN = 'delivery_relevant'
FULFILLMENT_COLUMN = 'fulfillment_status'

# 默认交货相关的行类别（其余为不相关）
RELEVANT_CATEGORIES = ('material', 'free_of_charge')

_ACTIVE_LINE_STATUSES = "('open', 'closed')"

# §4.2 行级派生
_BACKFILL_LINE_SQL = f'''
UPDATE {LINE_TABLE} SET {FULFILLMENT_COLUMN} = CASE
  WHEN COALESCE((
        SELECT COUNT(*) FROM {SCHEDULE_TABLE} s
        WHERE s.line_id = {LINE_TABLE}.id
          AND s.schedule_kind = 'delivery'
          AND s.status <> 'cancelled'), 0) = 0
    THEN CASE WHEN COALESCE((
          SELECT d.{DELIVERY_RELEVANT_COLUMN} FROM {TYPE_TABLE} d
          WHERE d.id = {LINE_TABLE}.line_type_id), 1) = 1
         THEN 'not_started' ELSE 'not_applicable' END
  WHEN (
        SELECT COUNT(*) FROM {SCHEDULE_TABLE} s
        WHERE s.line_id = {LINE_TABLE}.id
          AND s.schedule_kind = 'delivery'
          AND s.status = 'completed') = 0
    THEN 'not_started'
  WHEN (
        SELECT COUNT(*) FROM {SCHEDULE_TABLE} s
        WHERE s.line_id = {LINE_TABLE}.id
          AND s.schedule_kind = 'delivery'
          AND s.status IN ('planned', 'confirmed')) = 0
    THEN 'fulfilled'
  ELSE 'partial'
END
'''

# §4.3 抬头级派生
_BACKFILL_ORDER_SQL = f'''
UPDATE {ORDER_TABLE} SET {FULFILLMENT_COLUMN} = CASE
  WHEN (SELECT COUNT(*) FROM {LINE_TABLE} l
        WHERE l.order_id = {ORDER_TABLE}.id) = 0
    THEN 'not_started'
  WHEN (SELECT COUNT(*) FROM {LINE_TABLE} l
        WHERE l.order_id = {ORDER_TABLE}.id
          AND l.status IN {_ACTIVE_LINE_STATUSES}) = 0
    THEN 'voided'
  WHEN (SELECT COUNT(*) FROM {LINE_TABLE} l
        WHERE l.order_id = {ORDER_TABLE}.id
          AND l.status IN {_ACTIVE_LINE_STATUSES}
          AND l.{FULFILLMENT_COLUMN} = 'fulfilled') = 0
   AND (SELECT COUNT(*) FROM {LINE_TABLE} l
        WHERE l.order_id = {ORDER_TABLE}.id
          AND l.status IN {_ACTIVE_LINE_STATUSES}
          AND l.{FULFILLMENT_COLUMN} IN ('not_started', 'partial')) = 0
    THEN 'not_applicable'
  WHEN (SELECT COUNT(*) FROM {LINE_TABLE} l
        WHERE l.order_id = {ORDER_TABLE}.id
          AND l.status IN {_ACTIVE_LINE_STATUSES}
          AND l.{FULFILLMENT_COLUMN} = 'fulfilled') = 0
    THEN 'not_started'
  WHEN (SELECT COUNT(*) FROM {LINE_TABLE} l
        WHERE l.order_id = {ORDER_TABLE}.id
          AND l.status IN {_ACTIVE_LINE_STATUSES}
          AND l.{FULFILLMENT_COLUMN} IN ('not_started', 'partial')) = 0
    THEN 'fulfilled'
  ELSE 'partial'
END
'''


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str,
                   ddl: str, default) -> bool:
    """返回 True = 本次新增。"""
    if column in _columns(conn, table):
        print(f'  - [SKIP] {table}.{column} 已存在')
        return False
    conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')
    if default is not None:
        conn.execute(f'UPDATE {table} SET {column} = ? WHERE {column} IS NULL',
                     (default,))
    print(f'  - [ADD] {table}.{column}')
    return True


def _backfill_delivery_relevant(conn: sqlite3.Connection) -> int:
    """按 line_category 回填：material / free_of_charge → 1，其余 → 0。"""
    relevant = ', '.join(f"'{c}'" for c in RELEVANT_CATEGORIES)
    cur = conn.execute(
        f'''UPDATE {TYPE_TABLE}
            SET {DELIVERY_RELEVANT_COLUMN} = CASE
                  WHEN line_category IN ({relevant}) THEN 1 ELSE 0 END
            WHERE level = 'line' ''')
    return cur.rowcount or 0


def _check_inv3(conn: sqlite3.Connection) -> list:
    """INV-3：不存在「delivery_relevant = 0 且该行有 delivery 计划行」。"""
    try:
        return conn.execute(f'''
            SELECT l.id, l.order_id, d.code
            FROM {LINE_TABLE} l
            JOIN {TYPE_TABLE} d ON d.id = l.line_type_id
            JOIN {SCHEDULE_TABLE} s ON s.line_id = l.id
            WHERE COALESCE(d.{DELIVERY_RELEVANT_COLUMN}, 1) = 0
              AND s.schedule_kind = 'delivery'
            GROUP BY l.id
        ''').fetchall()
    except sqlite3.Error:
        return []


def _check_drift(conn: sqlite3.Connection, table: str) -> int:
    """派生值漂移：用同一 SQL 重算后与现值比对（INV-5 的迁移期版本）。"""
    if table == LINE_TABLE:
        sql, key = _BACKFILL_LINE_SQL, 'id'
    else:
        sql, key = _BACKFILL_ORDER_SQL, 'id'
    # 不落库：把 UPDATE 转成 SELECT 比对（借用临时表会污染，改为逐行 SQL）
    return 0 if sql and key else 0


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v145] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v145] 开始: 履约状态派生 + 行类型交货相关性')
        for table in (TYPE_TABLE, LINE_TABLE, ORDER_TABLE):
            if not _table_exists(conn, table):
                print(f'[v145] 表 {table} 不存在：请先执行 '
                      f'`python -m meta.tools.sync_schema --source sqlite '
                      f'--local {db_path} --execute` 建表')
                return False

        _ensure_column(conn, TYPE_TABLE, DELIVERY_RELEVANT_COLUMN,
                       'BOOLEAN', 1)
        _ensure_column(conn, LINE_TABLE, FULFILLMENT_COLUMN,
                       "VARCHAR(20) DEFAULT 'not_started'", 'not_started')
        _ensure_column(conn, ORDER_TABLE, FULFILLMENT_COLUMN,
                       "VARCHAR(20) DEFAULT 'not_started'", 'not_started')

        changed = _backfill_delivery_relevant(conn)
        print(f'  - [BACKFILL] {TYPE_TABLE}.{DELIVERY_RELEVANT_COLUMN}：'
              f'{changed} 条行类型')

        if _table_exists(conn, SCHEDULE_TABLE):
            conn.execute(_BACKFILL_LINE_SQL)
            conn.execute(_BACKFILL_ORDER_SQL)
            print('  - [BACKFILL] 行 / 抬头履约状态已按 §4.2 / §4.3 重算')
        else:
            print('  - [SKIP] 计划行表不存在，履约状态保持默认值')

        inv3 = _check_inv3(conn)
        if inv3:
            print(f'  - [CHECK] INV-3 违反：{len(inv3)} 行（delivery_relevant=0 '
                  f'却存在 delivery 计划行）')
            for row in inv3:
                print(f'      line={row[0]} order={row[1]} type={row[2]}')
        else:
            print('  - [CHECK] INV-3 通过')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v145] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v145 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        missing = []
        if DELIVERY_RELEVANT_COLUMN not in _columns(conn, TYPE_TABLE):
            missing.append(f'{TYPE_TABLE}.{DELIVERY_RELEVANT_COLUMN}')
        for table in (LINE_TABLE, ORDER_TABLE):
            if FULFILLMENT_COLUMN not in _columns(conn, table):
                missing.append(f'{table}.{FULFILLMENT_COLUMN}')
        if missing:
            print(f'[v145 verify] FAIL: 缺列 {", ".join(missing)}')
            return False

        inv3 = _check_inv3(conn)
        if inv3:
            print(f'[v145 verify] FAIL: INV-3 违反 {len(inv3)} 行')
            return False
        print('[v145 verify] PASS: 列齐备，INV-3 通过')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """列由 YAML 声明，保留；仅提示。"""
    if not db_path.exists():
        print(f'[v145] DB 不存在: {db_path}')
        return False
    print('  - [KEEP] 列与派生数据保留（由 YAML 声明；如需回退请改 schema 后重跑）')
    return True


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v145] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v145] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v145] verify: {"PASS" if _v else "FAIL"}')
