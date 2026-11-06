# -*- coding: utf-8 -*-
"""收货单测试替身：内存 SQLite + DataSource 形状包装 + 种子数据。

只供 meta/tests/test_receipt_*.py 使用；不触碰真实库。
"""

import sqlite3

SCHEMA = """
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT,
    document_type_id INTEGER,
    org_id INTEGER,
    purchase_org_id INTEGER,
    purchase_legal_entity_id INTEGER,
    supplier_party_id INTEGER,
    project_id INTEGER,
    deliver_to_location_id INTEGER,
    status TEXT,
    origin_purchase_order_id INTEGER,
    origin_receipt_id INTEGER,
    return_reason TEXT,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE purchase_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_type_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty REAL,
    status TEXT,
    fulfillment_status TEXT DEFAULT 'not_started',
    fulfillment_derived_at TEXT,
    updated_at TEXT
);
CREATE TABLE purchase_order_schedules (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_id INTEGER,
    schedule_kind TEXT,
    promised_date TEXT,
    promised_qty REAL,
    received_qty REAL DEFAULT 0,
    rejected_qty REAL DEFAULT 0,
    returned_qty REAL DEFAULT 0,
    completion_source TEXT,
    completion_prev_status TEXT,
    status TEXT,
    updated_at TEXT
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY,
    code TEXT,
    scope_bo TEXT,
    level TEXT,
    document_category TEXT,
    delivery_relevant INTEGER DEFAULT 1,
    number_sequence_id INTEGER
);
CREATE TABLE number_sequences (
    id INTEGER PRIMARY KEY,
    code TEXT,
    pattern TEXT,
    scope_fields TEXT,
    date_field TEXT,
    start_value INTEGER,
    on_exhaust TEXT
);
CREATE TABLE receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no TEXT NOT NULL,
    document_type_id INTEGER,
    receipt_date TEXT NOT NULL,
    actual_arrival_date TEXT,
    source_doc_type TEXT,
    source_doc_id INTEGER,
    source_doc_no TEXT,
    supplier_party_id INTEGER,
    supplier_delivery_no TEXT,
    org_id INTEGER,
    purchase_org_id INTEGER,
    inventory_org_id INTEGER,
    deliver_to_location_id INTEGER,
    project_id INTEGER,
    received_by TEXT,
    status TEXT,
    reversal_of_receipt_id INTEGER,
    return_to TEXT DEFAULT 'supplier',
    remark TEXT,
    created_at TEXT,
    updated_at TEXT,
    reversed_at TEXT
);
CREATE TABLE receipt_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER,
    line_no TEXT,
    schedule_id INTEGER,
    source_line_id INTEGER,
    order_id INTEGER,
    order_line_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty_received REAL,
    qty_rejected REAL DEFAULT 0,
    rejection_reason_code TEXT,
    rejection_disposition TEXT,
    lot_no TEXT,
    serial_no TEXT,
    putaway_location_id INTEGER,
    status TEXT,
    reversal_of_line_id INTEGER,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE demand_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demand_bo TEXT,
    demand_id INTEGER,
    demand_line_id INTEGER,
    demand_line_no TEXT,
    demand_need_date TEXT,
    project_id INTEGER,
    project_task_id INTEGER,
    target_bo TEXT,
    target_id INTEGER,
    target_line_id INTEGER,
    target_schedule_id INTEGER,
    qty REAL,
    uom_id INTEGER,
    allocated_amount REAL,
    cost_center_id INTEGER,
    expense_account_code TEXT,
    asset_category_code TEXT,
    charge_basis TEXT,
    status TEXT,
    reversed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE locations (
    id INTEGER PRIMARY KEY,
    status TEXT,
    org_id INTEGER
);
CREATE TABLE party_relations (
    id INTEGER PRIMARY KEY,
    role TEXT,
    party1_id INTEGER,
    party2_id INTEGER,
    status TEXT
);
CREATE TABLE control_parameter_defs (
    id INTEGER PRIMARY KEY,
    code TEXT,
    default_value TEXT,
    status TEXT
);
CREATE TABLE control_parameter_values (
    id INTEGER PRIMARY KEY,
    control_parameter_id INTEGER,
    value TEXT,
    status TEXT
);
CREATE TABLE orgs (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    status TEXT DEFAULT 'active'
);
CREATE TABLE org_functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER,
    function_type TEXT,
    status TEXT DEFAULT 'active'
);
"""


class _Tx:
    """最小事务上下文：外层开 BEGIN IMMEDIATE，嵌套只透传。"""

    def __init__(self, ds):
        self.ds = ds
        self.owned = False

    def __enter__(self):
        if not self.ds.conn.in_transaction:
            self.ds.conn.execute('BEGIN IMMEDIATE')
            self.owned = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.owned:
            if exc_type:
                self.ds.conn.rollback()
            else:
                self.ds.conn.commit()
        return False


class MemDS:
    """sqlite3 连接 → DataSource 形状（execute 返回 cursor 以取 lastrowid）。"""

    def __init__(self, conn):
        self.conn = conn

    @property
    def in_transaction(self):
        return bool(self.conn.in_transaction)

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))

    def commit(self):
        self.conn.commit()

    def transaction(self):
        return _Tx(self)


def build_db():
    # isolation_level=None = 自动提交：避免测试里的裸 INSERT/UPDATE 留下未提交
    # 事务，被 NumberSequenceEngine 判为「取号嵌在调用方事务内」而拒绝。
    conn = sqlite3.connect(':memory:', isolation_level=None)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def add_types(conn, delivered_seq=1, return_seq=1):
    """收货头类型（standard / red 共用 RCV 序列）+ 采购退货类型 + PO 行类型。"""
    conn.execute(
        'INSERT INTO number_sequences (id, code, pattern, scope_fields, '
        "date_field, start_value, on_exhaust) VALUES (1, 'RCV', "
        "'RCV-{DATE:yyyymm}-{SEQ:6}', NULL, 'receipt_date', 1, 'error')")
    conn.execute(
        'INSERT INTO number_sequences (id, code, pattern, scope_fields, '
        "date_field, start_value, on_exhaust) VALUES (2, 'RPO', "
        "'RPO-{DATE:yyyymm}-{SEQ:6}', NULL, 'order_date', 1, 'error')")
    conn.execute(
        'INSERT INTO number_sequences (id, code, pattern, scope_fields, '
        "date_field, start_value, on_exhaust) VALUES (3, 'RTV', "
        "'RTV-{DATE:yyyymm}-{SEQ:6}', NULL, 'receipt_date', 1, 'error')")
    conn.execute(
        'INSERT INTO type_definitions (id, code, scope_bo, level, '
        'document_category, delivery_relevant, number_sequence_id) '
        "VALUES (1, 'RCV_STD', 'receipt', 'header', 'standard', NULL, 1)")
    conn.execute(
        'INSERT INTO type_definitions (id, code, scope_bo, level, '
        'document_category, delivery_relevant, number_sequence_id) '
        "VALUES (2, 'RCV_RETURN', 'receipt', 'header', 'red', NULL, 1)")
    conn.execute(
        'INSERT INTO type_definitions (id, code, scope_bo, level, '
        'document_category, delivery_relevant, number_sequence_id) '
        "VALUES (3, 'RETURN_PO', 'purchase_order', 'header', 'return', NULL, 2)")
    conn.execute(
        'INSERT INTO type_definitions (id, code, scope_bo, level, '
        'document_category, delivery_relevant, number_sequence_id) '
        "VALUES (4, 'VENDOR_RETURN', 'receipt', 'header', 'return', NULL, 3)")
    conn.execute(
        'INSERT INTO type_definitions (id, code, scope_bo, level, '
        'document_category, delivery_relevant, number_sequence_id) '
        "VALUES (10, 'PO_GOODS', 'purchase_order', 'line', NULL, 1, NULL)")


def add_order(conn, oid=1, order_no='PO-0001', org_id=1, purchase_org_id=1,
              supplier_party_id=500, project_id=None, deliver_to_location_id=7,
              status='confirmed', purchase_legal_entity_id=None,
              document_type_id=None, origin_purchase_order_id=None,
              origin_receipt_id=None, return_reason=None):
    conn.execute(
        'INSERT INTO purchase_orders (id, order_no, document_type_id, org_id, '
        'purchase_org_id, purchase_legal_entity_id, supplier_party_id, project_id, '
        'deliver_to_location_id, status, origin_purchase_order_id, '
        'origin_receipt_id, return_reason) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [oid, order_no, document_type_id, org_id, purchase_org_id,
         purchase_legal_entity_id, supplier_party_id, project_id,
         deliver_to_location_id, status, origin_purchase_order_id,
         origin_receipt_id, return_reason])


def add_order_line(conn, lid=100, oid=1, item_id=900, uom_id=3, qty=100.0,
                   line_type_id=10, status='open'):
    conn.execute(
        'INSERT INTO purchase_order_lines (id, order_id, line_type_id, item_id, '
        'uom_id, qty, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [lid, oid, line_type_id, item_id, uom_id, qty, status])


def add_schedule(conn, sid=1, oid=1, lid=100, kind='delivery',
                 promised_date='2026-11-05', promised_qty=100.0,
                 received_qty=0.0, rejected_qty=0.0, status='planned',
                 completion_source=None, completion_prev_status=None):
    conn.execute(
        'INSERT INTO purchase_order_schedules (id, order_id, line_id, '
        'schedule_kind, promised_date, promised_qty, received_qty, rejected_qty, '
        'completion_source, completion_prev_status, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [sid, oid, lid, kind, promised_date, promised_qty, received_qty,
         rejected_qty, completion_source, completion_prev_status, status])


def add_vendor(conn, party_id=500):
    conn.execute(
        'INSERT INTO party_relations (role, party1_id, party2_id, status) '
        "VALUES ('vendor', ?, 1, 'active')", [party_id])


def add_location(conn, location_id=7, status='active', org_id=None):
    conn.execute('INSERT INTO locations (id, status, org_id) VALUES (?, ?, ?)',
                 [location_id, status, org_id])


def add_tolerance(conn, percent=0, param_id=1):
    conn.execute(
        'INSERT INTO control_parameter_defs (id, code, default_value, status) '
        "VALUES (?, 'receipt_over_tolerance_percent', ?, 'active')",
        [param_id, str(percent)])


def add_org(conn, org_id, parent_id=None, status='active'):
    conn.execute(
        'INSERT INTO orgs (id, parent_id, status) VALUES (?, ?, ?)',
        [org_id, parent_id, status])


def add_org_function(conn, org_id, function_type='inventory',
                     status='active'):
    conn.execute(
        'INSERT INTO org_functions (org_id, function_type, status) '
        'VALUES (?, ?, ?)', [org_id, function_type, status])


def add_org_tree(conn):
    """法人 1 / 10；2 为法人 1 下的库存组织；3 停用；4 无 inventory 职能；
    11 属法人 10（跨法人）。"""
    add_org(conn, 1)
    add_org_function(conn, 1, 'legal_entity')
    add_org(conn, 2, parent_id=1)
    add_org_function(conn, 2, 'inventory')
    add_org(conn, 3, parent_id=1, status='inactive')
    add_org_function(conn, 3, 'inventory')
    add_org(conn, 4, parent_id=1)
    add_org(conn, 10)
    add_org_function(conn, 10, 'legal_entity')
    add_org(conn, 11, parent_id=10)
    add_org_function(conn, 11, 'inventory')


def add_po_allocation(conn, schedule_id=1, demand_line_id=1, qty=100.0,
                      demand_bo='requisition', demand_id=1, uom_id=3):
    conn.execute(
        'INSERT INTO demand_allocations (demand_bo, demand_id, demand_line_id, '
        'demand_line_no, project_id, target_bo, target_id, target_line_id, '
        'target_schedule_id, qty, uom_id, charge_basis, status) '
        "VALUES (?, ?, ?, ?, NULL, 'purchase_order', 1, 100, ?, ?, ?, "
        "'inventory', 'active')",
        [demand_bo, demand_id, demand_line_id, 'L%s' % demand_line_id,
         schedule_id, qty, uom_id])


def seeded_db(percent=0, with_vendor=True, with_po_allocation=True,
              promised_qty=100.0):
    """标准场景：PO + 行 + 到货计划行 + 合法 vendor + 库位 + 可选容差。"""
    conn = build_db()
    add_types(conn)
    add_org_tree(conn)
    add_order(conn)
    add_order_line(conn)
    add_schedule(conn, promised_qty=promised_qty)
    # TBD-7 库位归属种子：7 未归属（默认收货库位，校验放行）/ 8 属库存组织 2
    # （正确）/ 9 属组织 4（跨组织，用于反例）
    add_location(conn)
    add_location(conn, 8, org_id=2)
    add_location(conn, 9, org_id=4)
    if with_vendor:
        add_vendor(conn)
    if with_po_allocation:
        add_po_allocation(conn, qty=promised_qty)
    add_tolerance(conn, percent)
    conn.commit()
    return conn
