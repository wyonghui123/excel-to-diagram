# -*- coding: utf-8 -*-
"""[v252 2026-11-11] 采购发票对象模型（W1：建表 + 索引）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §3 头字段 / §4 行字段 / §4.3 line_source_policy / §13 实施波次 W1

范围:
  1. 建 2 张表：vendor_invoices / vendor_invoice_lines
     （表由 meta/schemas/vendor_invoice{,_line}.yaml 声明，
      本迁移做兜底 CREATE + 显式索引，防止仅 sync_schema 漏建）
  2. 索引：uq_vendor_invoice_no / uq_vendor_invoice_reversal（部分唯一）
     / uq_line_no / 状态与匹配查询索引 / 行来源 FK 索引
  3. 不建 payment_block（TBD-3 已裁决）；不建 paid_amount / payment_status /
     gl_voucher_no / invoice_type / hold_flags（§3.3 显式否定）
  4. 不写种子数据：类型 / 序列 / 参数在 v253，doc_flow 在 v254

幂等:
  表 / 索引先查后建；重复执行打印 [SKIP]。

回滚:
  丢索引 + 删行表 / 头表（不删其他波次的种子数据）。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v252__vendor_invoice_object'

HEADER_TABLE = 'vendor_invoices'
LINE_TABLE = 'vendor_invoice_lines'

HEADER_DDL = """
CREATE TABLE IF NOT EXISTS vendor_invoices (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no VARCHAR(30) NOT NULL,
    document_type_id INTEGER NOT NULL,
    document_category VARCHAR(20) NOT NULL DEFAULT 'invoice',
    direction INTEGER NOT NULL DEFAULT 1,
    invoice_date DATE NOT NULL,
    received_date DATE,
    posting_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'posted', 'cancelled', 'reversed')),
    match_status VARCHAR(20) NOT NULL DEFAULT 'unmatched'
        CHECK (match_status IN ('unmatched', 'matched', 'exception', 'overridden')),
    match_mode VARCHAR(20) NOT NULL DEFAULT 'gr_based'
        CHECK (match_mode IN ('po_based', 'gr_based')),
    supplier_account_id INTEGER NOT NULL,
    supplier_party_id INTEGER NOT NULL,
    supplier_site_text VARCHAR(512),
    supplier_tax_no VARCHAR(64),
    currency_id INTEGER NOT NULL,
    exchange_rate NUMERIC(18,8),
    exchange_rate_type VARCHAR(20),
    exchange_rate_date DATE,
    purchase_org_id INTEGER,
    org_id INTEGER NOT NULL,
    supplier_invoice_no VARCHAR(60),
    net_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    gross_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    rounding_diff NUMERIC(18,4) NOT NULL DEFAULT 0,
    match_pricing_mode VARCHAR(20) NOT NULL DEFAULT 'po_price'
        CHECK (match_pricing_mode IN ('po_price', 'receipt_price', 'manual')),
    match_exception_reason VARCHAR(200),
    match_matched_at DATETIME,
    match_matched_by VARCHAR(200),
    settlement_mode VARCHAR(20) NOT NULL DEFAULT 'supplier_invoice'
        CHECK (settlement_mode IN ('supplier_invoice', 'ers')),
    reversal_of_invoice_id INTEGER,
    remark TEXT,
    created_at DATETIME,
    updated_at DATETIME
)
"""

LINE_DDL = """
CREATE TABLE IF NOT EXISTS vendor_invoice_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    schedule_id INTEGER,
    order_line_id INTEGER,
    receipt_line_id INTEGER,
    invoice_line_id INTEGER,
    return_line_id INTEGER,
    item_id INTEGER,
    item_group_id INTEGER,
    line_type_id INTEGER,
    description VARCHAR(500),
    qty NUMERIC(18,4) NOT NULL DEFAULT 0,
    uom_id INTEGER,
    unit_price NUMERIC(18,6) NOT NULL DEFAULT 0,
    price_includes_tax INTEGER NOT NULL DEFAULT 0
        CHECK (price_includes_tax IN (0, 1)),
    net_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    gross_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    po_unit_price NUMERIC(18,6),
    price_diff_amount NUMERIC(18,4),
    price_diff_percent NUMERIC(9,4),
    qty_over_receipt NUMERIC(18,4),
    match_status VARCHAR(20) NOT NULL DEFAULT 'unmatched'
        CHECK (match_status IN ('unmatched', 'matched', 'exception', 'overridden')),
    match_exception_reason VARCHAR(200),
    override_reason VARCHAR(200),
    overridden_by VARCHAR(200),
    overridden_at DATETIME,
    tax_code_id INTEGER,
    currency_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME
)
"""

TABLES = (
    (HEADER_TABLE, HEADER_DDL),
    (LINE_TABLE, LINE_DDL),
)

INDEXES = (
    ('uq_vendor_invoice_no', HEADER_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_invoice_no '
     'ON vendor_invoices(invoice_no)'),
    ('uq_vendor_invoice_reversal', HEADER_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_invoice_reversal '
     'ON vendor_invoices(reversal_of_invoice_id) '
     'WHERE reversal_of_invoice_id IS NOT NULL'),
    ('idx_vendor_invoice_status_date', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_status_date '
     'ON vendor_invoices(status, invoice_date)'),
    ('idx_vendor_invoice_supplier_status', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_supplier_status '
     'ON vendor_invoices(supplier_account_id, status)'),
    ('idx_vendor_invoice_supplier_no', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_supplier_no '
     'ON vendor_invoices(supplier_account_id, supplier_invoice_no)'),
    ('idx_vendor_invoice_document_type', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_document_type '
     'ON vendor_invoices(document_type_id)'),
    ('idx_vendor_invoice_purchase_org', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_purchase_org '
     'ON vendor_invoices(purchase_org_id)'),
    ('idx_vendor_invoice_org_status', HEADER_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_org_status '
     'ON vendor_invoices(org_id, status)'),
    ('uq_line_no', LINE_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_line_no '
     'ON vendor_invoice_lines(invoice_id, line_no)'),
    ('idx_vendor_invoice_line_schedule', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_line_schedule '
     'ON vendor_invoice_lines(schedule_id)'),
    ('idx_vendor_invoice_line_order', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_line_order '
     'ON vendor_invoice_lines(order_line_id)'),
    ('idx_vendor_invoice_line_receipt', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_line_receipt '
     'ON vendor_invoice_lines(receipt_line_id)'),
    ('idx_vendor_invoice_line_invoice_line', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_line_invoice_line '
     'ON vendor_invoice_lines(invoice_line_id)'),
    ('idx_vendor_invoice_line_return', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_line_return '
     'ON vendor_invoice_lines(return_line_id)'),
    ('idx_vendor_invoice_line_item', LINE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_vendor_invoice_line_item '
     'ON vendor_invoice_lines(item_id)'),
)

#: verify 断言的头表必含列（含显式否定项的反向断言）
HEADER_COLUMNS = {
    'id', 'invoice_no', 'document_type_id', 'document_category', 'direction',
    'invoice_date', 'received_date', 'posting_date', 'status', 'match_status',
    'match_mode', 'supplier_account_id', 'supplier_party_id',
    'supplier_site_text', 'supplier_tax_no', 'currency_id', 'exchange_rate',
    'exchange_rate_type', 'exchange_rate_date', 'purchase_org_id', 'org_id',
    'supplier_invoice_no', 'net_amount', 'tax_amount', 'gross_amount',
    'rounding_diff', 'match_pricing_mode', 'match_exception_reason',
    'match_matched_at', 'match_matched_by', 'settlement_mode',
    'reversal_of_invoice_id', 'remark', 'created_at', 'updated_at',
    'created_by', 'updated_by',
}

LINE_COLUMNS = {
    'id', 'invoice_id', 'line_no', 'schedule_id', 'order_line_id',
    'receipt_line_id', 'invoice_line_id', 'return_line_id', 'item_id',
    'item_group_id', 'line_type_id', 'description', 'qty', 'uom_id',
    'unit_price', 'price_includes_tax', 'net_amount', 'tax_amount',
    'gross_amount', 'po_unit_price', 'price_diff_amount', 'price_diff_percent',
    'qty_over_receipt', 'match_status', 'match_exception_reason',
    'override_reason', 'overridden_by', 'overridden_at', 'tax_code_id',
    'currency_id', 'created_at', 'updated_at', 'created_by', 'updated_by',
}

#: §3.3 显式否定：这些列不得出现
FORBIDDEN_HEADER_COLUMNS = {
    'payment_block', 'paid_amount', 'payment_status', 'gl_voucher_no',
    'invoice_type', 'hold_flags', 'total_invoiced_qty',
}


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


def _index_exists(conn, index):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        [index]).fetchone()
    return row is not None


# ------------------------------------------------------------------- migrate

def _do_tables(conn):
    created = 0
    for table, ddl in TABLES:
        if _table_exists(conn, table):
            print('[v252] SKIP: 表 %s 已存在' % table)
            continue
        conn.execute(ddl)
        print('[v252] CREATE: 表 %s' % table)
        created += 1
    return created


def _do_indexes(conn):
    created = 0
    for index, table, ddl in INDEXES:
        if not _table_exists(conn, table):
            print('[v252] SKIP: 表 %s 不存在（跳过索引 %s）' % (table, index))
            continue
        if _index_exists(conn, index):
            print('[v252] SKIP: 索引 %s 已存在' % index)
            continue
        conn.execute(ddl)
        print('[v252] CREATE: 索引 %s' % index)
        created += 1
    return created


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """建表 + 索引（幂等）。"""
    db_path = Path(db_path)
    print('[v252] 开始: 采购发票对象模型（W1 建表）')
    conn = _connect(db_path)
    try:
        _do_tables(conn)
        _do_indexes(conn)
        conn.commit()
        print('[v252] 完成: 采购发票对象模型（W1 建表）')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def verify(db_path: Path) -> bool:
    """校验表 / 列 / 索引，且不含显式否定列。"""
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        for table in (HEADER_TABLE, LINE_TABLE):
            if not _table_exists(conn, table):
                problems.append('缺少表 %s' % table)
        if _table_exists(conn, HEADER_TABLE):
            missing = HEADER_COLUMNS - _columns(conn, HEADER_TABLE)
            if missing:
                problems.append('%s 缺少列: %s'
                                % (HEADER_TABLE, ', '.join(sorted(missing))))
            forbidden = FORBIDDEN_HEADER_COLUMNS & _columns(conn, HEADER_TABLE)
            if forbidden:
                problems.append('%s 含禁止列: %s'
                                % (HEADER_TABLE, ', '.join(sorted(forbidden))))
        if _table_exists(conn, LINE_TABLE):
            missing = LINE_COLUMNS - _columns(conn, LINE_TABLE)
            if missing:
                problems.append('%s 缺少列: %s'
                                % (LINE_TABLE, ', '.join(sorted(missing))))
        for index, table, _ddl in INDEXES:
            if _table_exists(conn, table) and not _index_exists(conn, index):
                problems.append('缺少索引 %s' % index)
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v252] FAIL: %s' % problem)
        return False
    print('[v252] PASS: 采购发票两表 / 索引 / 枚举列齐备')
    return True


# ------------------------------------------------------------------ rollback

def rollback(db_path: Path) -> bool:
    """丢索引 + 删表（种子数据由后续迁移自行回滚）。"""
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        for index, table, _ddl in reversed(INDEXES):
            if _table_exists(conn, table) and _index_exists(conn, index):
                conn.execute('DROP INDEX IF EXISTS %s' % index)
                print('[v252] DROP: 索引 %s' % index)
        for table in (LINE_TABLE, HEADER_TABLE):
            if _table_exists(conn, table):
                conn.execute('DROP TABLE IF EXISTS %s' % table)
                print('[v252] DROP: 表 %s' % table)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()