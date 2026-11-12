# -*- coding: utf-8 -*-
"""v238 —— 销售发票行改价差额（price_diff_amount）。

背景：
  D13 价格变更（Fusion 对标）：草稿发票行允许覆盖订单单价，但必须填写改价原因；
  改价差额按 `(unit_price - 订单单价) × 数量` 派生，供审批与对账使用。

内容：
  1. 给 customer_invoice_lines 增加 price_diff_amount（NOT NULL DEFAULT 0）。
  2. 回填：有订单价的行按差额公式计算；手工行（order_unit_price 为空）置 0。
  3. verify 校验列存在、无空值、与公式一致。
  4. rollback 删除该列。

幂等：列已存在则跳过 ALTER 与回填。
"""

import sqlite3
from pathlib import Path

LINE_TABLE = 'customer_invoice_lines'
COLUMN = 'price_diff_amount'

_DIFF_EXPR_SQL = (
    'ROUND((unit_price - COALESCE(order_unit_price, unit_price)) * qty, 4)'
)


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _column_exists(conn, table, column):
    if not _table_exists(conn, table):
        return False
    rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    return any(row[1] == column for row in rows)


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v238] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, LINE_TABLE):
            print('[v238] SKIP: table %s not found（请先执行 v236）' % LINE_TABLE)
            return False

        if _column_exists(conn, LINE_TABLE, COLUMN):
            print('[v238] column %s.%s already exists, skip ALTER'
                  % (LINE_TABLE, COLUMN))
            conn.commit()
            return True

        conn.execute(
            "ALTER TABLE %s ADD COLUMN %s NUMERIC(18,4) NOT NULL DEFAULT 0"
            % (LINE_TABLE, COLUMN))
        print('[v238] added column %s.%s' % (LINE_TABLE, COLUMN))

        conn.execute(
            'UPDATE %s SET %s = %s' % (LINE_TABLE, COLUMN, _DIFF_EXPR_SQL))
        conn.commit()
    finally:
        conn.close()

    print('[v238] done')
    return True


def migrate(db_path, skip_backup=True):
    """与 v236 保持同名入口。"""
    return upgrade(db_path, skip_backup=skip_backup)


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v238] verify FAIL: database not found')
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, LINE_TABLE):
            print('[v238] verify FAIL: table %s missing' % LINE_TABLE)
            return False
        if not _column_exists(conn, LINE_TABLE, COLUMN):
            print('[v238] verify FAIL: column %s missing' % COLUMN)
            return False

        nulls = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE %s IS NULL' % (LINE_TABLE, COLUMN)
        ).fetchone()[0]
        if nulls:
            print('[v238] verify FAIL: %s NULL rows' % nulls)
            return False

        mismatch = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE ABS(%s - %s) > 0.0001'
            % (LINE_TABLE, COLUMN, _DIFF_EXPR_SQL)).fetchone()[0]
        if mismatch:
            print('[v238] verify FAIL: %s diff mismatches' % mismatch)
            return False

        print('[v238] verify OK')
        return True
    finally:
        conn.close()


def rollback(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v238] rollback SKIP: database not found')
        return False

    conn = _connect(path)
    try:
        if not _column_exists(conn, LINE_TABLE, COLUMN):
            print('[v238] rollback SKIP: column missing')
            return True
        try:
            conn.execute(
                'ALTER TABLE %s DROP COLUMN %s' % (LINE_TABLE, COLUMN))
            conn.commit()
            print('[v238] rollback done')
            return True
        except sqlite3.OperationalError as exc:
            print('[v238] rollback FAIL: %s' % exc)
            return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(target)
    verify(target)
