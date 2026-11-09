# -*- coding: utf-8 -*-
"""销售发票测试夹具（内存 SQLite + DataSource 形状）。

放 factories 目录的原因：本文件需要直接建表/播种，属于 conftest raw-SQL
守卫的白名单路径（`meta/tests/factories/`），避免各测试文件重复声明
ALLOW_RAW_SQL 并各写一份 DDL 造成漂移。

表结构：customer_invoice 三张表 + 派生列直接复用 `v231__customer_invoice`
的 DDL 常量；其余上游表（订单 / 发货 / 付款条件 / 类型 / 序列 / 权限）
按服务真实读取的列做最小化建表。
"""
import sqlite3
from contextlib import contextmanager

from meta.migrations.v231__customer_invoice import (
    HEADER_DDL, LINE_DDL, SCHEDULE_DDL)

INVOICE_DATE = '2026-11-09'
CUSTOMER_ID = 900
CURRENCY_ID = 1
ORG_ID = 10

ORDER_ID = 1
ORDER_LINE_DELIVERY = 11
ORDER_LINE_PLAN = 12
ORDER_LINE_NONE = 13

SHIPMENT_ID = 1
SHIP_LINE_ID = 81
SHIP_LINE_SECOND = 82

DELIVERY_SCHEDULE_ID = 71
BILLING_SCHEDULE_ID = 72

PAYMENT_TERM_ID = 5

_UPSTREAM_DDL = """
CREATE TABLE IF NOT EXISTS type_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(200),
    scope_bo VARCHAR(64),
    level VARCHAR(16),
    document_category VARCHAR(32),
    line_category VARCHAR(32),
    delivery_relevant INTEGER DEFAULT 1,
    number_sequence_id INTEGER,
    default_type_id INTEGER,
    status VARCHAR(20) DEFAULT 'active',
    description TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS number_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(32) UNIQUE,
    name VARCHAR(128),
    pattern VARCHAR(128),
    scope_fields TEXT,
    date_field VARCHAR(64),
    start_value INTEGER DEFAULT 1,
    on_exhaust VARCHAR(16) DEFAULT 'error',
    preview TEXT,
    status VARCHAR(20) DEFAULT 'active',
    description TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS sales_orders (
    id INTEGER PRIMARY KEY,
    order_no VARCHAR(30),
    customer_account_id INTEGER,
    bill_to_account_id INTEGER,
    payer_account_id INTEGER,
    bill_to_address_text VARCHAR(512),
    tax_registration_no VARCHAR(64),
    currency_id INTEGER,
    exchange_rate NUMERIC(18,8) DEFAULT 1,
    exchange_rate_type VARCHAR(20),
    exchange_rate_date DATETIME,
    payment_term_id INTEGER,
    incoterm_code VARCHAR(16),
    org_id INTEGER,
    sales_org_id INTEGER,
    project_id INTEGER,
    billing_method VARCHAR(16) DEFAULT 'delivery',
    billing_status VARCHAR(16) NOT NULL DEFAULT 'none',
    billing_derived_at DATETIME
);

CREATE TABLE IF NOT EXISTS sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_no INTEGER,
    item_id INTEGER,
    description VARCHAR(512),
    uom_id INTEGER,
    qty NUMERIC(18,4),
    unit_price NUMERIC(18,6),
    tax_code_id INTEGER,
    tax_rate_percent NUMERIC(9,4),
    project_id INTEGER,
    project_task_id INTEGER,
    billing_method VARCHAR(16) DEFAULT 'delivery',
    billing_relevance VARCHAR(16) NOT NULL DEFAULT 'delivery',
    billed_qty NUMERIC(18,4) NOT NULL DEFAULT 0,
    billed_amount NUMERIC(18,4) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales_order_schedules (
    id INTEGER PRIMARY KEY,
    order_line_id INTEGER,
    schedule_kind VARCHAR(16) DEFAULT 'delivery',
    billed_amount NUMERIC(18,4) NOT NULL DEFAULT 0,
    billing_status VARCHAR(16) NOT NULL DEFAULT 'none'
);

CREATE TABLE IF NOT EXISTS shipments (
    id INTEGER PRIMARY KEY,
    delivery_no VARCHAR(30),
    order_id INTEGER,
    status VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS shipment_lines (
    id INTEGER PRIMARY KEY,
    delivery_id INTEGER,
    order_line_id INTEGER,
    schedule_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty NUMERIC(18,4),
    billed_qty NUMERIC(18,4) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payment_terms (
    id INTEGER PRIMARY KEY,
    code VARCHAR(32),
    basis_date_rule VARCHAR(32) DEFAULT 'invoice_date',
    cutoff_day INTEGER
);

CREATE TABLE IF NOT EXISTS payment_term_lines (
    id INTEGER PRIMARY KEY,
    payment_term_id INTEGER,
    seq INTEGER,
    percentage NUMERIC(9,4),
    offset_months INTEGER DEFAULT 0,
    fixed_day_of_month INTEGER,
    offset_days INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(128) UNIQUE,
    name VARCHAR(128),
    resource_type VARCHAR(64),
    action VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(64) UNIQUE,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS permission_set_permissions (
    permission_set_id INTEGER,
    permission_id INTEGER,
    permission_code VARCHAR(128),
    granted INTEGER DEFAULT 1,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS doc_flow_rule (
    rule_id VARCHAR(64) PRIMARY KEY,
    source_bo VARCHAR(64),
    target_bo VARCHAR(64),
    source_qty_field VARCHAR(64),
    pool VARCHAR(32),
    status VARCHAR(16) DEFAULT 'active',
    field_map TEXT,
    split_key TEXT,
    target_line_bo VARCHAR(64),
    head_fk_field VARCHAR(64),
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS menus (
    menu_code VARCHAR(64) PRIMARY KEY,
    menu_name VARCHAR(128),
    menu_path VARCHAR(200),
    parent_menu VARCHAR(200),
    sort_order INTEGER DEFAULT 99
);
"""


class MemoryDataSource:
    """sqlite3 连接 → DataSource 形状；支持 transaction/commit（取号内核依赖）。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.in_transaction = False

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or ()))
        columns = [item[0] for item in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or ()))

    def commit(self):
        self.conn.commit()

    @contextmanager
    def transaction(self):
        if self.in_transaction:
            yield
            return
        self.in_transaction = True
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self.in_transaction = False


def build_conn(*, shipment_qty: float = 40.0,
               with_shipment: bool = True,
               with_payment_term: bool = True,
               payment_term_lines=None) -> sqlite3.Connection:
    """建库并播种一套可直接开票的最小主数据（内存）。"""
    conn = sqlite3.connect(':memory:')
    _init(conn, shipment_qty=shipment_qty, with_shipment=with_shipment,
          with_payment_term=with_payment_term,
          payment_term_lines=payment_term_lines)
    return conn


def build_file(path, **kwargs) -> sqlite3.Connection:
    """同上，落盘版本（迁移测试需要真实文件路径）。"""
    conn = sqlite3.connect(str(path))
    _init(conn, **kwargs)
    return conn


def _init(conn, *, shipment_qty: float = 40.0,
          with_shipment: bool = True,
          with_payment_term: bool = True,
          payment_term_lines=None) -> None:
    conn.executescript(
        HEADER_DDL + ';' + LINE_DDL + ';' + SCHEDULE_DDL + ';' + _UPSTREAM_DDL)
    _seed_types(conn)
    _seed_sequences(conn)
    _seed_order(conn)
    if with_shipment:
        _seed_shipment(conn, shipment_qty)
    if with_payment_term:
        _seed_payment_term(conn, payment_term_lines)
    conn.commit()


def build_bare_file(path) -> sqlite3.Connection:
    """迁移专用：只有上游表与两条订单行，发票三表交给 migrate() 创建。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(_UPSTREAM_DDL)
    conn.execute(
        "INSERT INTO sales_orders (id, order_no, billing_status) "
        "VALUES (?, ?, 'none')", [ORDER_ID, 'SO-0001'])
    conn.execute(
        'INSERT INTO sales_order_lines '
        '(id, order_id, line_no, qty, billing_method, billing_relevance, '
        ' billed_qty, billed_amount) VALUES (?, ?, 1, 100, ?, ?, 0, 0)',
        [ORDER_LINE_DELIVERY, ORDER_ID, 'milestone', 'delivery'])
    conn.execute(
        'INSERT INTO sales_order_lines '
        '(id, order_id, line_no, qty, billing_method, billing_relevance, '
        ' billed_qty, billed_amount) VALUES (?, ?, 2, 50, ?, ?, 0, 0)',
        [ORDER_LINE_PLAN, ORDER_ID, 'delivery', 'delivery'])
    conn.execute(
        "INSERT INTO sales_order_schedules "
        "(id, order_line_id, schedule_kind, billed_amount, billing_status) "
        "VALUES (?, ?, 'billing', 0, 'none')",
        [BILLING_SCHEDULE_ID, ORDER_LINE_DELIVERY])
    for code in ('admin', 'default'):
        conn.execute(
            'INSERT INTO permission_sets (code, is_active) VALUES (?, 1)',
            [code])
    conn.commit()
    return conn


def build_permission_file(path, menu_rows=None) -> sqlite3.Connection:
    """v234 专用：上游表 + 权限集 + 菜单种子（menu_rows: (code, name, parent, order)）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(_UPSTREAM_DDL)
    for code in ('admin', 'default'):
        conn.execute(
            'INSERT INTO permission_sets (code, is_active) VALUES (?, 1)',
            [code])
    for menu_code, menu_name, parent, order in (menu_rows or ()):
        conn.execute(
            'INSERT INTO menus (menu_code, menu_name, parent_menu, sort_order) '
            'VALUES (?, ?, ?, ?)', [menu_code, menu_name, parent, order])
    conn.commit()
    return conn


def make_ds(conn: sqlite3.Connection) -> MemoryDataSource:
    return MemoryDataSource(conn)


# ---------------------------------------------------------------- 读 / 改夹具

def fetch_one(conn, sql, params=None):
    cur = conn.execute(sql, list(params or ()))
    columns = [item[0] for item in cur.description]
    row = cur.fetchone()
    return dict(zip(columns, row)) if row else None


def fetch_all(conn, sql, params=None):
    cur = conn.execute(sql, list(params or ()))
    columns = [item[0] for item in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_header(conn, invoice_id):
    return fetch_one(conn, 'SELECT * FROM customer_invoices WHERE id = ?',
                     [invoice_id])


def get_lines(conn, invoice_id):
    return fetch_all(
        conn,
        'SELECT * FROM customer_invoice_lines WHERE invoice_id = ? '
        'ORDER BY line_no, id', [invoice_id])


def get_schedules(conn, invoice_id):
    return fetch_all(
        conn,
        'SELECT * FROM customer_invoice_schedules WHERE invoice_id = ? '
        'ORDER BY schedule_no', [invoice_id])


def set_shipment_status(conn, status, shipment_id=SHIPMENT_ID):
    conn.execute('UPDATE shipments SET status = ? WHERE id = ?',
                 [status, shipment_id])


def set_shipment_line_billed(conn, qty, line_id=SHIP_LINE_ID):
    conn.execute('UPDATE shipment_lines SET billed_qty = ? WHERE id = ?',
                 [qty, line_id])


def shipment_billed(conn, line_id=SHIP_LINE_ID):
    row = conn.execute('SELECT billed_qty FROM shipment_lines WHERE id = ?',
                       [line_id]).fetchone()
    return float(row[0])


def set_order_terms(conn, *, basis_date_rule='invoice_date',
                    cutoff_day=None, term_id=PAYMENT_TERM_ID):
    conn.execute(
        'UPDATE payment_terms SET basis_date_rule = ?, cutoff_day = ? '
        'WHERE id = ?', [basis_date_rule, cutoff_day, term_id])


def set_payment_term_line(conn, line_id, **values):
    columns = ', '.join('%s = ?' % key for key in values)
    conn.execute('UPDATE payment_term_lines SET %s WHERE id = ?' % columns,
                 list(values.values()) + [line_id])


def set_header_amounts(conn, invoice_id, *, net=None, tax=None, gross=None):
    conn.execute(
        'UPDATE customer_invoices SET net_amount = COALESCE(?, net_amount), '
        'tax_amount = COALESCE(?, tax_amount), '
        'gross_amount = COALESCE(?, gross_amount) WHERE id = ?',
        [net, tax, gross, invoice_id])


def set_order_line_billed(conn, line_id, qty, amount=0):
    conn.execute(
        'UPDATE sales_order_lines SET billed_qty = ?, billed_amount = ? '
        'WHERE id = ?', [qty, amount, line_id])


def set_order_line_item(conn, item_id, line_id=ORDER_LINE_DELIVERY):
    conn.execute('UPDATE sales_order_lines SET item_id = ? WHERE id = ?',
                 [item_id, line_id])


def type_id(conn, code):
    row = conn.execute(
        "SELECT id FROM type_definitions WHERE scope_bo = 'customer_invoice' "
        'AND code = ?', [code]).fetchone()
    return int(row[0])


def _seed_types(conn: sqlite3.Connection) -> None:
    rows = (
        ('SINV', 'header', 'standard', None),
        ('SCR', 'header', 'credit_memo', None),
        ('SDN', 'header', 'debit_memo', None),
        ('INV_ITEM', 'line', None, 'material'),
        ('INV_SERVICE', 'line', None, 'service'),
        ('INV_DISCOUNT', 'line', None, 'discount'),
    )
    for code, level, document_category, line_category in rows:
        conn.execute(
            'INSERT INTO type_definitions '
            '(code, name, scope_bo, level, document_category, line_category, '
            ' delivery_relevant, status) '
            "VALUES (?, ?, 'customer_invoice', ?, ?, ?, 1, 'active')",
            [code, code, level, document_category, line_category])


def _seed_sequences(conn: sqlite3.Connection) -> None:
    for code, name in (('SINV', '销售发票编号'),
                       ('SCR', '红字销售发票编号'),
                       ('SDN', '销售借项通知单编号')):
        conn.execute(
            'INSERT INTO number_sequences '
            '(code, name, pattern, date_field, start_value, on_exhaust, status) '
            "VALUES (?, ?, ?, 'invoice_date', 1, 'error', 'active')",
            [code, name, '%s-{DATE:yyyymm}-{SEQ:5}' % code])
        row = conn.execute(
            'SELECT id FROM number_sequences WHERE code = ?', [code]).fetchone()
        conn.execute(
            'UPDATE type_definitions SET number_sequence_id = ? '
            "WHERE scope_bo = 'customer_invoice' AND level = 'header' "
            'AND code = ?', [row[0], code])
    item_id = conn.execute(
        "SELECT id FROM type_definitions WHERE scope_bo = 'customer_invoice' "
        "AND level = 'line' AND code = 'INV_ITEM'").fetchone()[0]
    conn.execute(
        'UPDATE type_definitions SET default_type_id = ? '
        "WHERE scope_bo = 'customer_invoice' AND level = 'header' "
        "AND code = 'SINV'", [item_id])


def _seed_order(conn: sqlite3.Connection) -> None:
    conn.execute(
        'INSERT INTO sales_orders '
        '(id, order_no, customer_account_id, bill_to_account_id, '
        ' payer_account_id, bill_to_address_text, tax_registration_no, '
        ' currency_id, exchange_rate, exchange_rate_type, payment_term_id, '
        ' org_id, sales_org_id, billing_status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [ORDER_ID, 'SO-0001', CUSTOMER_ID, CUSTOMER_ID, CUSTOMER_ID,
         '上海市浦东新区世纪大道 100 号', '91310000TEST', CURRENCY_ID, 1.0,
         'spot', PAYMENT_TERM_ID, ORG_ID, ORG_ID, 'none'])
    lines = (
        (ORDER_LINE_DELIVERY, 'Widget', 100, 10.0, 'delivery'),
        (ORDER_LINE_PLAN, 'Milestone', 50, 20.0, 'plan'),
        (ORDER_LINE_NONE, 'Freebie', 5, 1.0, 'none'),
    )
    for line_id, description, qty, price, relevance in lines:
        conn.execute(
            'INSERT INTO sales_order_lines '
            '(id, order_id, line_no, item_id, description, uom_id, qty, '
            ' unit_price, tax_code_id, tax_rate_percent, billing_relevance, '
            ' billed_qty, billed_amount) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)',
            [line_id, ORDER_ID, line_id, 500 + line_id, description, 21,
             qty, price, 31, 13.0, relevance])
    conn.execute(
        'INSERT INTO sales_order_schedules '
        '(id, order_line_id, schedule_kind, billed_amount, billing_status) '
        "VALUES (?, ?, 'delivery', 0, 'none')",
        [DELIVERY_SCHEDULE_ID, ORDER_LINE_DELIVERY])
    conn.execute(
        'INSERT INTO sales_order_schedules '
        '(id, order_line_id, schedule_kind, billed_amount, billing_status) '
        "VALUES (?, ?, 'billing', 0, 'none')",
        [BILLING_SCHEDULE_ID, ORDER_LINE_PLAN])


def _seed_shipment(conn: sqlite3.Connection, qty: float) -> None:
    conn.execute(
        'INSERT INTO shipments (id, delivery_no, order_id, status) '
        'VALUES (?, ?, ?, ?)',
        [SHIPMENT_ID, 'DN-0001', ORDER_ID, 'shipped'])
    conn.execute(
        'INSERT INTO shipment_lines '
        '(id, delivery_id, order_line_id, schedule_id, item_id, uom_id, qty, '
        ' billed_qty) VALUES (?, ?, ?, ?, ?, ?, ?, 0)',
        [SHIP_LINE_ID, SHIPMENT_ID, ORDER_LINE_DELIVERY,
         DELIVERY_SCHEDULE_ID, 511, 21, qty])
    conn.execute(
        'INSERT INTO shipment_lines '
        '(id, delivery_id, order_line_id, schedule_id, item_id, uom_id, qty, '
        ' billed_qty) VALUES (?, ?, ?, ?, ?, ?, ?, 0)',
        [SHIP_LINE_SECOND, SHIPMENT_ID, ORDER_LINE_DELIVERY,
         DELIVERY_SCHEDULE_ID, 511, 21, 10.0])


def _seed_payment_term(conn: sqlite3.Connection, lines=None) -> None:
    conn.execute(
        "INSERT INTO payment_terms (id, code, basis_date_rule, cutoff_day) "
        "VALUES (?, ?, 'invoice_date', NULL)",
        [PAYMENT_TERM_ID, 'NET30'])
    rows = lines or ((1, 30, 0, None, 0), (2, 70, 1, None, 0))
    for index, (seq, percentage, months, fixed_day, days) in enumerate(rows):
        conn.execute(
            'INSERT INTO payment_term_lines '
            '(id, payment_term_id, seq, percentage, offset_months, '
            ' fixed_day_of_month, offset_days) VALUES (?, ?, ?, ?, ?, ?, ?)',
            [500 + index, PAYMENT_TERM_ID, seq, percentage, months, fixed_day,
             days])


# ---------------------------------------------------------------- v232 迁移辅助

def table_columns(path, table):
    conn = sqlite3.connect(str(path))
    try:
        return {row[1] for row in conn.execute(
            'PRAGMA table_info(%s)' % table).fetchall()}
    finally:
        conn.close()


def drop_column(path, table, column):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute('ALTER TABLE %s DROP COLUMN %s' % (table, column))
        conn.commit()
    finally:
        conn.close()


def insert_invoice_without_category(path, invoice_no, type_code):
    """按 v231 旧表结构插入发票（不含 document_category）。"""
    conn = sqlite3.connect(str(path))
    try:
        type_id = conn.execute(
            "SELECT id FROM type_definitions "
            "WHERE scope_bo = 'customer_invoice' AND code = ?",
            [type_code]).fetchone()[0]
        conn.execute(
            """
            INSERT INTO customer_invoices (
                invoice_no, document_type_id, invoice_date, status,
                customer_account_id, currency_id, org_id,
                net_amount, tax_amount, gross_amount
            ) VALUES (?, ?, '2026-11-01', 'draft', 1, 1, 1, 0, 0, 0)
            """, [invoice_no, type_id])
        conn.commit()
    finally:
        conn.close()


def invoice_categories(path):
    conn = sqlite3.connect(str(path))
    try:
        return dict(conn.execute(
            'SELECT invoice_no, document_category FROM customer_invoices'))
    finally:
        conn.close()


def insert_line_without_price_diff(path, invoice_no, qty, unit_price,
                                   order_unit_price=None):
    """按 v231 旧结构插入「发票 + 行」，行不含 price_diff_amount。"""
    conn = sqlite3.connect(str(path))
    try:
        header_type_id = conn.execute(
            "SELECT id FROM type_definitions "
            "WHERE scope_bo = 'customer_invoice' AND code = 'SINV'").fetchone()[0]
        line_type_id = conn.execute(
            "SELECT id FROM type_definitions "
            "WHERE scope_bo = 'customer_invoice' AND code = 'INV_ITEM'").fetchone()[0]
        cursor = conn.execute(
            """
            INSERT INTO customer_invoices (
                invoice_no, document_type_id, invoice_date, status,
                customer_account_id, currency_id, org_id,
                net_amount, tax_amount, gross_amount
            ) VALUES (?, ?, '2026-11-01', 'draft', 1, 1, 1, 0, 0, 0)
            """, [invoice_no, header_type_id])
        invoice_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO customer_invoice_lines (
                invoice_id, line_no, line_type_id, source_doc_type,
                description, uom_id, qty, unit_price, order_unit_price,
                tax_code_id, tax_rate_percent
            ) VALUES (?, 1, ?, 'manual', 'line', 1, ?, ?, ?, 1, 13)
            """, [invoice_id, line_type_id, qty, unit_price, order_unit_price])
        conn.commit()
        return invoice_id
    finally:
        conn.close()


def line_price_diffs(path):
    conn = sqlite3.connect(str(path))
    try:
        return [float(row[0]) for row in conn.execute(
            'SELECT price_diff_amount FROM customer_invoice_lines '
            'ORDER BY id')]
    finally:
        conn.close()


# ---------------------------------------------------------------- v235 迁移辅助

def doc_flow_rule(path, rule_id):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            'SELECT source_bo, target_bo, source_qty_field, pool, status '
            'FROM doc_flow_rule WHERE rule_id = ?', [rule_id]).fetchone()
        return dict(zip(
            ('source_bo', 'target_bo', 'source_qty_field', 'pool', 'status'),
            row)) if row else None
    finally:
        conn.close()


def doc_flow_rule_count(path, rule_id):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            'SELECT COUNT(*) FROM doc_flow_rule WHERE rule_id = ?',
            [rule_id]).fetchone()[0]
    finally:
        conn.close()


def set_doc_flow_rule_status(path, rule_id, status):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute('UPDATE doc_flow_rule SET status = ? WHERE rule_id = ?',
                     [status, rule_id])
        conn.commit()
    finally:
        conn.close()
