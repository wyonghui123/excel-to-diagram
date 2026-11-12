# -*- coding: utf-8 -*-
"""v247 —— 销售订单计划行开票固定金额（里程碑期次）。

依据:
  docs/specs/sales-invoice-pricing-spec-2026-11-10.md
    §10 TBD-11 缺口 C（里程碑固定金额）
    §11.3.3（缺口表：里程碑金额无落库载体）

内容:
  1. `sales_order_schedules` 增 `billing_fixed_amount REAL`：
     仅 `schedule_kind='billing'` 使用，与 `billing_percent` 二选一；
     固定金额不随订单行净额缩放（比例期次仍按 percent 派生金额）。
  2. 存量数据体检（只报告、不阻断升级）：
     - 冲突行：比例与固定金额同时有值（R-SCH-11 不允许）
     - 空洞行：计费行两者皆空（升级前已存在则保留现状，由业务侧补齐）

幂等：列先查后加；重复执行打印 [SKIP]。
回滚：尽力 DROP COLUMN（SQLite 3.35+）；不删业务数据。

列 DDL 真源：meta/schemas/sales_order_schedule.yaml（number / decimal_places=4）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v247__sales_order_schedule_billing_fixed_amount'

SCHEDULE_TABLE = 'sales_order_schedules'
NEW_COLUMNS = (
    ('billing_fixed_amount', 'REAL'),
)


# --------------------------------------------------------------------- helpers

def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}


def _add_columns(conn, table, columns):
    if not _table_exists(conn, table):
        print('[v247] SKIP: %s 表不存在（未加列）' % table)
        return 0
    have = _columns(conn, table)
    added = 0
    for column, ddl in columns:
        if column in have:
            print('[v247] SKIP: %s.%s 已存在' % (table, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, ddl))
        print('[v247] + %s.%s' % (table, column))
        added += 1
    return added


def _drop_column(conn, table, column):
    if not _table_exists(conn, table) or column not in _columns(conn, table):
        return
    try:
        conn.execute('ALTER TABLE %s DROP COLUMN %s' % (table, column))
        print('[v247] - %s.%s' % (table, column))
    except sqlite3.OperationalError as exc:
        print('[v247] WARN: 无法删除 %s.%s（%s）' % (table, column, exc))


# ------------------------------------------------------------------- upgrade

def _report_legacy_rows(conn):
    """存量计费行体检：冲突（比例+固定额）与两者皆空。只报告不阻断。"""
    if 'billing_fixed_amount' not in _columns(conn, SCHEDULE_TABLE):
        return
    conflict = conn.execute(
        "SELECT COUNT(*) FROM %s WHERE schedule_kind = 'billing' "
        "  AND status <> 'cancelled' "
        "  AND billing_percent IS NOT NULL "
        "  AND billing_fixed_amount IS NOT NULL" % SCHEDULE_TABLE).fetchone()[0]
    empty = conn.execute(
        "SELECT COUNT(*) FROM %s WHERE schedule_kind = 'billing' "
        "  AND status <> 'cancelled' "
        "  AND billing_percent IS NULL "
        "  AND billing_fixed_amount IS NULL" % SCHEDULE_TABLE).fetchone()[0]
    if conflict:
        print('[v247] WARN: %d 条计费行同时有比例与固定金额（R-SCH-11 冲突，需业务修正）'
              % conflict)
    if empty:
        print('[v247] WARN: %d 条计费行比例与固定金额皆空（需业务补齐）' % empty)
    if not conflict and not empty:
        print('[v247] 存量计费行口径校验通过')


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v247] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, SCHEDULE_TABLE):
            print('[v247] SKIP: %s 表不存在' % SCHEDULE_TABLE)
            return False
        _add_columns(conn, SCHEDULE_TABLE, NEW_COLUMNS)
        _report_legacy_rows(conn)
        conn.commit()
        print('[v247] 完成')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def verify(db_path):
    path = Path(db_path)
    if not path.exists():
        return False
    conn = _connect(path)
    try:
        if not _table_exists(conn, SCHEDULE_TABLE):
            print('[v247 verify] FAIL: 缺表 %s' % SCHEDULE_TABLE)
            return False
        have = _columns(conn, SCHEDULE_TABLE)
        for column, _ddl in NEW_COLUMNS:
            if column not in have:
                print('[v247 verify] FAIL: 缺列 %s.%s' % (SCHEDULE_TABLE, column))
                return False
        conflict = conn.execute(
            "SELECT COUNT(*) FROM %s WHERE schedule_kind = 'billing' "
            "  AND status <> 'cancelled' "
            "  AND billing_percent IS NOT NULL "
            "  AND billing_fixed_amount IS NOT NULL" % SCHEDULE_TABLE).fetchone()[0]
        if conflict:
            print('[v247 verify] FAIL: %d 条计费行口径冲突' % conflict)
            return False
        print('[v247 verify] OK')
        return True
    finally:
        conn.close()


# ------------------------------------------------------------------ rollback

def rollback(db_path):
    path = Path(db_path)
    if not path.exists():
        return False
    conn = _connect(path)
    try:
        for column, _ddl in NEW_COLUMNS:
            _drop_column(conn, SCHEDULE_TABLE, column)
        conn.commit()
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)