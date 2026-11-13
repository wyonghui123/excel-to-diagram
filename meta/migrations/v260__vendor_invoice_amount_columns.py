# -*- coding: utf-8 -*-
"""[v260 2026-11-12] 采购发票金额链路（W2：内核钩子所需列）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §22.2 / §22.3 / §22.11
  docs/superpowers/plans/2026-11-12-vendor-invoice-amount-w2-execution-plan.md F5

内容:
  1. vendor_invoices 增列:
       supplier_gross_amount NUMERIC(18,4)  供应商票面总额（头级）
     幂等: PRAGMA 判列，缺失才 ALTER。
  2. vendor_invoice_lines 增列:
       tax_rate_percent NUMERIC(9,4)        行税率快照（含税倒算必需）
     幂等同上。

说明:
  · 金额算术复用 SalesOrderAmountService 内核（D-VI-27），本迁移只补字段，
    不建任何金额视图 / 金额服务。
  · 两列均可空：历史行按 0 / NULL 处理，由服务层在写入时按税率快照重算。

回滚:
  SQLite 老版本不支持 DROP COLUMN，列保留并清空值。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v260__vendor_invoice_amount_columns'

HEADER_TABLE = 'vendor_invoices'
LINE_TABLE = 'vendor_invoice_lines'

HEADER_COLUMNS = (
    ('supplier_gross_amount', 'NUMERIC(18,4)'),
)
LINE_COLUMNS = (
    ('tax_rate_percent', 'NUMERIC(9,4)'),
)


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


# ------------------------------------------------------------------ migration

def _do_columns(conn, table, columns):
    if not _table_exists(conn, table):
        print('[v260] SKIP: %s 表不存在（未加列）' % table)
        return 0
    existing = _columns(conn, table)
    added = 0
    for column, column_type in columns:
        if column in existing:
            print('[v260] SKIP: %s.%s 已存在' % (table, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (table, column, column_type))
        added += 1
        print('[v260] ALTER: %s 新增 %s' % (table, column))
    return added


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v260] 开始: 采购发票金额列（supplier_gross_amount / tax_rate_percent）')
    conn = _connect(db_path)
    try:
        _do_columns(conn, HEADER_TABLE, HEADER_COLUMNS)
        _do_columns(conn, LINE_TABLE, LINE_COLUMNS)
        conn.commit()
        print('[v260] 完成: 采购发票金额列')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        for table, columns in ((HEADER_TABLE, HEADER_COLUMNS),
                               (LINE_TABLE, LINE_COLUMNS)):
            if not _table_exists(conn, table):
                problems.append('缺少表 %s' % table)
                continue
            existing = _columns(conn, table)
            for column, _type in columns:
                if column not in existing:
                    problems.append('缺少列 %s.%s' % (table, column))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v260] FAIL: %s' % problem)
        return False
    print('[v260] PASS: vendor_invoices.supplier_gross_amount / '
          'vendor_invoice_lines.tax_rate_percent 齐备')
    return True


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v260] 开始: 回滚采购发票金额列（清值，列保留）')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, HEADER_TABLE):
            conn.execute('UPDATE %s SET supplier_gross_amount = NULL'
                         % HEADER_TABLE)
        if _table_exists(conn, LINE_TABLE):
            conn.execute('UPDATE %s SET tax_rate_percent = NULL' % LINE_TABLE)
        conn.commit()
        print('[v260] 完成: 两列已清空（SQLite 老版本不支持 DROP COLUMN）')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()