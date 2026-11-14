# -*- coding: utf-8 -*-
"""[v271 2026-11-14] 采购发票应付期次（AP Payment Plan）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §23
  （与 AR customer_invoice_schedules 逐字段对称；R-VI-34~37）

范围:
  1. 新建 vendor_invoice_schedules（父字段 invoice_id，金额列 amount，
     累计列 amount_applied，状态枚举 open/partial/closed/cancelled）。
  2. vendor_invoices 增列 payment_term_id INTEGER（可空，空 = 即期）。
  3. vendor_accounts 增列 default_payment_term_id INTEGER（可空）。
  4. 本迁移只建表加列，不下推历史数据、不写任何期次。

回滚:
  删 3 索引 + 删 vendor_invoice_schedules 表；2 个列保留
  （SQLite 老版本不支持 DROP COLUMN）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v271__vendor_invoice_schedule'

HEADER_TABLE = 'vendor_invoices'
ACCOUNT_TABLE = 'vendor_accounts'
SCHEDULE_TABLE = 'vendor_invoice_schedules'

HEADER_COLUMNS = (
    ('payment_term_id', 'INTEGER'),
)

ACCOUNT_COLUMNS = (
    ('default_payment_term_id', 'INTEGER'),
)

SCHEDULE_DDL = """
CREATE TABLE IF NOT EXISTS vendor_invoice_schedules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    schedule_no INTEGER NOT NULL,
    payment_term_line_id INTEGER,
    ratio_percent NUMERIC(9,4) NOT NULL,
    due_date DATETIME NOT NULL,
    amount NUMERIC(18,4) NOT NULL,
    amount_applied NUMERIC(18,4) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'partial', 'closed', 'cancelled')),
    created_at DATETIME,
    updated_at DATETIME
)
"""

INDEXES = (
    ('uq_vendor_invoice_schedule_no',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_invoice_schedule_no '
     'ON vendor_invoice_schedules(invoice_id, schedule_no)'),
    ('idx_vendor_invoice_schedule_invoice',
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_schedule_invoice '
     'ON vendor_invoice_schedules(invoice_id)'),
    ('idx_vendor_invoice_schedule_status_due',
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_schedule_status_due '
     'ON vendor_invoice_schedules(status, due_date)'),
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


def _index_names(conn):
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'")}


def _do_columns(conn, table, columns):
    if not _table_exists(conn, table):
        print('[v271] SKIP: %s 表不存在（未加列）' % table)
        return 0
    existing = _columns(conn, table)
    added = 0
    for column, column_type in columns:
        if column in existing:
            print('[v271] SKIP: %s.%s 已存在' % (table, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (table, column, column_type))
        added += 1
        print('[v271] ALTER: %s 新增 %s' % (table, column))
    return added


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v271] 开始: 采购发票应付期次（表 + 2 列）')
    conn = _connect(db_path)
    try:
        conn.execute(SCHEDULE_DDL)
        print('[v271] CREATE: %s' % SCHEDULE_TABLE)
        for name, ddl in INDEXES:
            conn.execute(ddl)
            print('[v271] CREATE INDEX: %s' % name)
        _do_columns(conn, HEADER_TABLE, HEADER_COLUMNS)
        _do_columns(conn, ACCOUNT_TABLE, ACCOUNT_COLUMNS)
        conn.commit()
        print('[v271] 完成: vendor_invoice_schedules / '
              'vendor_invoices.payment_term_id / '
              'vendor_accounts.default_payment_term_id')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, SCHEDULE_TABLE):
            problems.append('缺少表 %s' % SCHEDULE_TABLE)
        for table, columns in ((HEADER_TABLE, HEADER_COLUMNS),
                               (ACCOUNT_TABLE, ACCOUNT_COLUMNS)):
            if not _table_exists(conn, table):
                problems.append('缺少表 %s' % table)
                continue
            existing = _columns(conn, table)
            for column, _type in columns:
                if column not in existing:
                    problems.append('缺少列 %s.%s' % (table, column))
        index_names = _index_names(conn)
        for name, _ddl in INDEXES:
            if name not in index_names:
                problems.append('缺少索引 %s' % name)
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v271] FAIL: %s' % problem)
        return False
    print('[v271] PASS: vendor_invoice_schedules / 2 列 / 3 索引齐备')
    return True


# ------------------------------------------------------------------- rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v271] 开始回滚: 删除期次表与索引（列保留）')
    conn = _connect(db_path)
    try:
        for name, _ddl in INDEXES:
            conn.execute('DROP INDEX IF EXISTS %s' % name)
            print('[v271] DROP INDEX: %s' % name)
        conn.execute('DROP TABLE IF EXISTS %s' % SCHEDULE_TABLE)
        print('[v271] DROP TABLE: %s' % SCHEDULE_TABLE)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    migrate(Path(target))
    verify(Path(target))