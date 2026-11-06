# -*- coding: utf-8 -*-
"""v224 - 库存余额入库日期投影（库龄 P0）

依据: docs/specs/p8-inventory-aging-model/spec.md §5.1 / §5.3 / §7 / §7.1

背景:
- inventory_balances 只有 updated_at，无法回答“这批货什么时候进来的、库龄多少”。
- 入库日期已是事实数据（inventory_transactions.transaction_date = receipt_date），
  只需把它投影到余额行 first_received_date。

动作:
  1. 断言 SQLite >= 3.33（UPDATE … FROM 依赖），低版本显式失败、不静默降级
  2. PRAGMA 判列；缺则 ALTER TABLE ADD COLUMN first_received_date DATE
  3. 用 §5.3 CTE（排除红冲入库、扣减红冲出库）回填最早未清零入库日；
     `a.first_received_date IS NOT NULL` 保证不把已有日期写成 NULL（T16）
  4. verify：列存在且可空 + 打印“qty>0 且日期 NULL”的待核查数
  5. 不建索引（idx_inv_balance_org_item 已覆盖报表路径）

回滚:
  不回滚列（SQLite 删列需重建表，风险高）；允许重跑回填，结果幂等。

[ALLOW_DESTRUCTIVE] rollback 仅提示，不改结构与数据。
"""
from __future__ import annotations

import os
import sqlite3

MIGRATION_NAME = 'v224__inventory_balance_received_date'

BAL_TABLE = 'inventory_balances'
TX_TABLE = 'inventory_transactions'
COLUMN = 'first_received_date'
COLUMN_DDL = 'DATETIME NULL'  # 与 generated_schema.sql 的 date 字段映射一致

KEY_COLUMNS = (
    'org_id', 'location_id', 'item_id', 'batch_id', 'stock_status',
    'stock_segment_type', 'project_id', 'project_task_id',
    'sales_order_line_id', 'owner_party_id',
)

REQUIRED_SQLITE = (3, 33, 0)


def _assert_sqlite_version():
    """UPDATE … FROM 需 SQLite >= 3.33；低版本显式失败并提示所需版本。"""
    if sqlite3.sqlite_version_info < REQUIRED_SQLITE:
        raise RuntimeError(
            '[v224] 需要 SQLite >= %s，当前 %s；本迁移依赖 UPDATE … FROM'
            % ('.'.join(str(x) for x in REQUIRED_SQLITE),
               sqlite3.sqlite_version))


def _table_exists(conn, name):
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone())


def _column_info(conn, table):
    return {row[1]: row for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def apply_column(conn, table=BAL_TABLE):
    """测试替身/迁移共用：幂等补 first_received_date 列。"""
    if not _table_exists(conn, table):
        return False
    if COLUMN in _column_info(conn, table):
        return True
    conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                 % (table, COLUMN, COLUMN_DDL))
    return True


def _do_column(conn):
    if not _table_exists(conn, BAL_TABLE):
        print('  - [SKIP] 缺表 %s，跳过补列' % BAL_TABLE)
        return False
    if COLUMN in _column_info(conn, BAL_TABLE):
        print('  - [SKIP] 列 %s.%s 已存在' % (BAL_TABLE, COLUMN))
        return True
    apply_column(conn)
    print('  - [ALTER] 列 %s.%s' % (BAL_TABLE, COLUMN))
    return True


def _backfill(conn):
    """用 §5.3 共用 SQL 回填；无事务历史的余额保持 NULL（期初口径）。"""
    if not _table_exists(conn, TX_TABLE) or not _table_exists(conn, BAL_TABLE):
        print('  - [SKIP] 缺 %s / %s，跳过回填' % (TX_TABLE, BAL_TABLE))
        return 0
    if COLUMN not in _column_info(conn, BAL_TABLE):
        print('  - [SKIP] 列缺失，跳过回填')
        return 0
    from meta.services.inventory_aging_service import InventoryAgingService

    select_sql = InventoryAgingService.first_received_date_sql(
        org_filter=False)
    match = ' AND '.join('b.%s = a.%s' % (col, col) for col in KEY_COLUMNS)
    update_sql = (
        'UPDATE %s AS b\n'
        'SET %s = a.first_received_date\n'
        'FROM (%s) AS a\n'
        'WHERE %s\n'
        '  AND b.qty_on_hand > 0\n'
        '  AND a.first_received_date IS NOT NULL'
        % (BAL_TABLE, COLUMN, select_sql, match))
    cursor = conn.execute(update_sql)
    print('  - [UPDATE] 回填余额行 %s 条' % cursor.rowcount)
    return cursor.rowcount


def _pending_count(conn):
    try:
        return conn.execute(
            'SELECT COUNT(*) FROM %s WHERE qty_on_hand > 0 '
            'AND %s IS NULL' % (BAL_TABLE, COLUMN)).fetchone()[0]
    except sqlite3.Error:
        return -1


def _do_upgrade(conn):
    _do_column(conn)
    _backfill(conn)
    pending = _pending_count(conn)
    print('  - [VERIFY] qty>0 且日期 NULL 的余额行（期初/待核查）: %s'
          % pending)
    return True


def migrate(db_path, skip_backup=False):
    print('[v224] 库存余额入库日期投影')
    _assert_sqlite_version()
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(db_path)
    try:
        _do_upgrade(conn)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path):
    if not os.path.exists(db_path):
        return {'ok': False, 'error': 'db not found'}
    conn = sqlite3.connect(db_path)
    try:
        info = _column_info(conn, BAL_TABLE)
        row = info.get(COLUMN)
        checks = {
            'column': row is not None,
            'nullable': bool(row) and int(row[3]) == 0,
        }
        pending = _pending_count(conn)
        return {'ok': all(checks.values()), 'checks': checks,
                'pending_rows': pending}
    finally:
        conn.close()


def rollback(db_path):
    print('[v224 rollback] 列保留（SQLite 删列需重建表）；回填可重复执行')
    return True


downgrade = rollback
