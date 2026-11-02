# -*- coding: utf-8 -*-
"""调拨单测试替身：内存 SQLite + DataSource 形状包装 + 种子数据。

只供 meta/tests/test_transfer_order_*.py 使用；不触碰真实库。
"""

import sqlite3

SCHEMA = """
CREATE TABLE transfer_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_order_no TEXT NOT NULL UNIQUE,
    document_type_id INTEGER,
    transfer_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    approval_status TEXT NOT NULL DEFAULT 'not_required',
    fulfillment_status TEXT,
    from_org_id INTEGER NOT NULL,
    to_org_id INTEGER NOT NULL,
    legal_entity_id INTEGER NOT NULL,
    from_location_id INTEGER,
    to_location_id INTEGER,
    project_id INTEGER,
    actual_ship_date TEXT,
    carrier_name TEXT,
    waybill_no TEXT,
    reversal_of_transfer_id INTEGER,
    remark TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE transfer_order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_order_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    line_type_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty REAL NOT NULL DEFAULT 0,
    qty_shipped REAL NOT NULL DEFAULT 0,
    qty_received REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    fulfillment_status TEXT,
    remark TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE (transfer_order_id, line_no)
);
CREATE TABLE transfer_shipments (
    created_by TEXT,
    updated_by TEXT,
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_no TEXT NOT NULL UNIQUE,
    transfer_order_id INTEGER NOT NULL,
    ship_date TEXT NOT NULL,
    carrier_name TEXT,
    waybill_no TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    remark TEXT,
    created_at TEXT,
    updated_at TEXT,
    CHECK (status IN ('draft', 'posted', 'cancelled'))
);
CREATE TABLE transfer_shipment_lines (
    created_by TEXT,
    updated_by TEXT,
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_shipment_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    transfer_order_line_id INTEGER NOT NULL,
    qty REAL NOT NULL DEFAULT 0,
    remark TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE (transfer_shipment_id, line_no),
    CHECK (qty > 0)
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    scope_bo TEXT,
    level TEXT,
    document_category TEXT,
    line_category TEXT,
    delivery_relevant INTEGER DEFAULT 1,
    number_sequence_id INTEGER,
    default_type_id INTEGER,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE number_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    pattern TEXT,
    scope_fields TEXT,
    date_field TEXT,
    start_value INTEGER,
    on_exhaust TEXT,
    preview TEXT,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE orgs (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    code TEXT,
    name TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE org_functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER,
    function_type TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    item_type TEXT,
    item_group_id INTEGER,
    status TEXT DEFAULT 'active'
);
CREATE TABLE uoms (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE locations (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    status TEXT DEFAULT 'active'
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
    deliver_to_location_id INTEGER,
    project_id INTEGER,
    received_by TEXT,
    status TEXT,
    reversal_of_receipt_id INTEGER,
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
CREATE TABLE approval_policies (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    scope_bo TEXT,
    trigger_action TEXT,
    status TEXT,
    priority INTEGER,
    effective_from TEXT,
    effective_to TEXT
);
CREATE TABLE approval_policy_conditions (
    id INTEGER PRIMARY KEY,
    policy_id INTEGER,
    group_no INTEGER,
    field_id TEXT,
    operator TEXT,
    value_number REAL,
    value_text TEXT,
    value_json TEXT
);
CREATE TABLE approval_policy_steps (
    id INTEGER PRIMARY KEY,
    policy_id INTEGER,
    step_no INTEGER,
    approver_type TEXT,
    approver_ref TEXT,
    min_amount REAL,
    max_amount REAL,
    approve_mode TEXT,
    sla_hours INTEGER
);
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT,
    app_id TEXT,
    executor_type TEXT NOT NULL,
    assign_policy TEXT,
    executor_candidates TEXT,
    executor_config TEXT,
    inputs TEXT,
    doc_ref TEXT,
    created_by TEXT,
    created_at TEXT,
    attempt INTEGER
);
CREATE TABLE line_type_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_type_id INTEGER NOT NULL,
    item_group_id INTEGER,
    specificity_rank INTEGER NOT NULL DEFAULT 100,
    line_type_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE demand_allocations (
    created_by TEXT,
    updated_by TEXT,
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demand_bo TEXT NOT NULL,
    demand_id INTEGER NOT NULL,
    demand_line_id INTEGER NOT NULL,
    demand_line_no TEXT,
    demand_need_date TEXT,
    project_id INTEGER,
    project_task_id INTEGER,
    target_bo TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    target_line_id INTEGER NOT NULL,
    target_schedule_id INTEGER,
    qty REAL NOT NULL,
    uom_id INTEGER,
    allocated_amount REAL,
    cost_center_id INTEGER,
    expense_account_code TEXT,
    asset_category_code TEXT,
    charge_basis TEXT NOT NULL DEFAULT 'inventory',
    status TEXT NOT NULL DEFAULT 'active',
    reversed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE requisition_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requisition_id INTEGER NOT NULL,
    line_no TEXT NOT NULL,
    line_type TEXT NOT NULL DEFAULT 'goods',
    item_id INTEGER,
    description TEXT,
    qty REAL NOT NULL,
    uom_id INTEGER,
    need_date TEXT,
    deliver_to_location_id INTEGER,
    requested_source_org_id INTEGER,
    resolved_source_org_id INTEGER,
    cost_center_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT,
    updated_at TEXT
);
"""

#: type_definitions 中固定 id（便于测试断言）
TO_STANDARD_TYPE_ID = 100
TO_GOODS_TYPE_ID = 110
TO_SERVICE_TYPE_ID = 111
TO_ASSET_TYPE_ID = 112
TO_TEXT_TYPE_ID = 113
PO_LINE_TYPE_ID = 10

#: number_sequences 中固定 id
TRF_SEQUENCE_ID = 5
RCV_SEQUENCE_ID = 1
TRS_SEQUENCE_ID = 6

#: 调拨发货单头 / 行类型（v193 种子）
TRS_STANDARD_TYPE_ID = 120
TRS_GOODS_TYPE_ID = 130

#: 收货单头类型
RCV_STANDARD_TYPE_ID = 1
RCV_RETURN_TYPE_ID = 2


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


# ---------------------------------------------------------------------------
# 类型 / 编号序列
# ---------------------------------------------------------------------------
def add_types(conn):
    """调拨单类型 + TRF 序列；附带收货单类型（桥接测试用）与 PO 行类型（反例）。"""
    conn.execute(
        'INSERT INTO number_sequences (id, code, name, pattern, scope_fields, '
        "date_field, start_value, on_exhaust, status) VALUES (?, 'RCV', '收货单编号', "
        "'RCV-{DATE:yyyymm}-{SEQ:6}', NULL, 'receipt_date', 1, 'error', 'active')",
        [RCV_SEQUENCE_ID])
    conn.execute(
        'INSERT INTO number_sequences (id, code, name, pattern, scope_fields, '
        "date_field, start_value, on_exhaust, status) VALUES (?, 'TRF', '调拨单编号', "
        "'TRF-{DATE:yyyymm}-{SEQ:6}', NULL, 'transfer_date', 1, 'error', 'active')",
        [TRF_SEQUENCE_ID])
    conn.execute(
        'INSERT INTO number_sequences (id, code, name, pattern, scope_fields, '
        "date_field, start_value, on_exhaust, status) VALUES (?, 'TRS', '调拨发货单编号', "
        "'TRS-{DATE:yyyymm}-{SEQ:6}', NULL, 'ship_date', 1, 'error', 'active')",
        [TRS_SEQUENCE_ID])

    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, delivery_relevant, number_sequence_id, '
        "default_type_id, status) VALUES (?, 'RCV_STD', '标准收货单', 'receipt', "
        "'header', 'standard', NULL, ?, NULL, 'active')",
        [RCV_STANDARD_TYPE_ID, RCV_SEQUENCE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, delivery_relevant, number_sequence_id, '
        "default_type_id, status) VALUES (?, 'RCV_RETURN', '红字收货单', 'receipt', "
        "'header', 'return', NULL, ?, NULL, 'active')",
        [RCV_RETURN_TYPE_ID, RCV_SEQUENCE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, line_category, delivery_relevant, status) '
        "VALUES (?, 'PO_GOODS', '采购物料行', 'purchase_order', 'line', NULL, "
        "'material', 1, 'active')",
        [PO_LINE_TYPE_ID])

    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, number_sequence_id, default_type_id, status) '
        "VALUES (?, 'TRF_STD', '标准调拨单', 'transfer_order', 'header', "
        "'standard', ?, ?, 'active')",
        [TO_STANDARD_TYPE_ID, TRF_SEQUENCE_ID, TO_GOODS_TYPE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, line_category, delivery_relevant, status) '
        "VALUES (?, 'TRF_GOODS', '标准物料行', 'transfer_order', 'line', NULL, "
        "'material', 1, 'active')",
        [TO_GOODS_TYPE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, line_category, delivery_relevant, status) '
        "VALUES (?, 'TRF_SERVICE', '服务行', 'transfer_order', 'line', NULL, "
        "'service', 0, 'active')",
        [TO_SERVICE_TYPE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, line_category, delivery_relevant, status) '
        "VALUES (?, 'TRF_ASSET', '资产行', 'transfer_order', 'line', NULL, "
        "'asset', 0, 'active')",
        [TO_ASSET_TYPE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, line_category, delivery_relevant, status) '
        "VALUES (?, 'TRF_TEXT', '文本行', 'transfer_order', 'line', NULL, "
        "'text', 0, 'active')",
        [TO_TEXT_TYPE_ID])

    # v193 调拨发货单类型（头绑定 TRS 序列 / 默认行类型）
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, number_sequence_id, default_type_id, status) '
        "VALUES (?, 'TRS_STD', '标准调拨发货单', 'transfer_shipment', 'header', "
        "'standard', ?, ?, 'active')",
        [TRS_STANDARD_TYPE_ID, TRS_SEQUENCE_ID, TRS_GOODS_TYPE_ID])
    conn.execute(
        'INSERT INTO type_definitions (id, code, name, scope_bo, level, '
        'document_category, line_category, delivery_relevant, status) '
        "VALUES (?, 'TRS_GOODS', '标准发货行', 'transfer_shipment', 'line', NULL, "
        "'material', 1, 'active')",
        [TRS_GOODS_TYPE_ID])

    conn.execute(
        'INSERT INTO line_type_assignments (document_type_id, item_group_id, '
        'specificity_rank, line_type_id, status) '
        "VALUES (?, NULL, 900, ?, 'active')",
        [TO_STANDARD_TYPE_ID, TO_GOODS_TYPE_ID])

    conn.execute(
        'INSERT INTO control_parameter_defs (id, code, default_value, status) '
        "VALUES (1, 'transfer_over_ship_percent', '0', 'active')")
    conn.execute(
        'INSERT INTO control_parameter_defs (id, code, default_value, status) '
        "VALUES (2, 'transfer_over_receive_percent', '0', 'active')")


# ---------------------------------------------------------------------------
# 审批配置（TBD-9）
# ---------------------------------------------------------------------------
def add_approval_policy(conn, policy_id=1, code='TRF_APPROVAL',
                        name='调拨审批策略', scope_bo='transfer_order',
                        trigger_action='submit', status='active', priority=0,
                        effective_from=None, effective_to=None):
    conn.execute(
        'INSERT INTO approval_policies (id, code, name, scope_bo, '
        'trigger_action, status, priority, effective_from, effective_to) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [policy_id, code, name, scope_bo, trigger_action, status, priority,
         effective_from, effective_to])


def add_approval_step(conn, policy_id=1, step_no=1, approver_type='role',
                      approver_ref='procurement_manager', min_amount=None,
                      max_amount=None, approve_mode='any', sla_hours=24,
                      step_id=None):
    conn.execute(
        'INSERT INTO approval_policy_steps (id, policy_id, step_no, '
        'approver_type, approver_ref, min_amount, max_amount, approve_mode, '
        'sla_hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [step_id, policy_id, step_no, approver_type, approver_ref, min_amount,
         max_amount, approve_mode, sla_hours])


# ---------------------------------------------------------------------------
# 组织 / 法人 / 主数据
# ---------------------------------------------------------------------------
def add_org(conn, org_id, parent_id=None, status='active'):
    conn.execute(
        'INSERT INTO orgs (id, parent_id, code, name, status) VALUES (?, ?, ?, ?, ?)',
        [org_id, parent_id, 'ORG%s' % org_id, '组织%s' % org_id, status])


def add_org_function(conn, org_id, function_type='inventory', status='active'):
    conn.execute(
        'INSERT INTO org_functions (org_id, function_type, status) '
        'VALUES (?, ?, ?)', [org_id, function_type, status])


def add_org_tree(conn):
    """法人 1 / 10；2、3、12 为法人 1 下的库存组织；4 停用；5 无 inventory 职能；
    6 无 legal_entity 祖先；11 属法人 10（跨法人）。"""
    add_org(conn, 1)
    add_org_function(conn, 1, 'legal_entity')
    for org_id in (2, 3, 12):
        add_org(conn, org_id, parent_id=1)
        add_org_function(conn, org_id, 'inventory')
    add_org(conn, 4, parent_id=1, status='inactive')
    add_org_function(conn, 4, 'inventory')
    add_org(conn, 5, parent_id=1)
    add_org(conn, 6)
    add_org_function(conn, 6, 'inventory')
    add_org(conn, 10)
    add_org_function(conn, 10, 'legal_entity')
    add_org(conn, 11, parent_id=10)
    add_org_function(conn, 11, 'inventory')


def add_item(conn, item_id=900, item_type='goods', status='active',
             item_group_id=None):
    conn.execute(
        'INSERT INTO items (id, code, name, item_type, item_group_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        [item_id, 'ITEM%s' % item_id, '物料%s' % item_id, item_type,
         item_group_id, status])


def add_uom(conn, uom_id=3, status='active'):
    conn.execute('INSERT INTO uoms (id, code, name, status) VALUES (?, ?, ?, ?)',
                 [uom_id, 'UOM%s' % uom_id, '单位%s' % uom_id, status])


def add_location(conn, location_id=7, status='active'):
    conn.execute(
        'INSERT INTO locations (id, code, name, status) VALUES (?, ?, ?, ?)',
        [location_id, 'LOC%s' % location_id, '库位%s' % location_id, status])


def add_master_data(conn):
    add_item(conn, 900, 'goods', 'active', item_group_id=7)
    add_item(conn, 901, 'service', 'active')
    add_item(conn, 902, 'goods', 'inactive')
    add_uom(conn, 3, 'active')
    add_location(conn, 6, 'active')
    add_location(conn, 7, 'active')
    add_location(conn, 8, 'inactive')


# ---------------------------------------------------------------------------
# 调拨单头 / 行
# ---------------------------------------------------------------------------
def add_transfer_order(conn, oid=1, order_no='TRF-202611-000001',
                       document_type_id=TO_STANDARD_TYPE_ID,
                       transfer_date='2026-11-01', status='draft',
                       approval_status='not_required',
                       from_org_id=2, to_org_id=3, legal_entity_id=1,
                       from_location_id=None, to_location_id=7,
                       fulfillment_status=None, actual_ship_date=None):
    conn.execute(
        'INSERT INTO transfer_orders (id, transfer_order_no, document_type_id, '
        'transfer_date, status, approval_status, fulfillment_status, from_org_id, '
        'to_org_id, legal_entity_id, from_location_id, to_location_id, '
        'actual_ship_date) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [oid, order_no, document_type_id, transfer_date, status,
         approval_status, fulfillment_status, from_org_id, to_org_id,
         legal_entity_id, from_location_id, to_location_id, actual_ship_date])


def add_transfer_line(conn, lid=100, oid=1, line_no=10,
                      line_type_id=TO_GOODS_TYPE_ID, item_id=900, uom_id=3,
                      qty=100.0, qty_shipped=0.0, qty_received=0.0,
                      status='open', fulfillment_status=None):
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, line_no, '
        'line_type_id, item_id, uom_id, qty, qty_shipped, qty_received, status, '
        'fulfillment_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [lid, oid, line_no, line_type_id, item_id, uom_id, qty, qty_shipped,
         qty_received, status, fulfillment_status])


def release_transfer_order(conn, oid=1, line_shipped=None):
    """把调拨单置 released，并按 `{line_id: qty_shipped}` 造发货事实。"""
    conn.execute("UPDATE transfer_orders SET status = 'released' WHERE id = ?",
                 [oid])
    for lid, qty in (line_shipped or {}).items():
        conn.execute(
            'UPDATE transfer_order_lines SET qty_shipped = ? WHERE id = ?',
            [float(qty), lid])
    conn.commit()


def seeded_db(line_qtys=(100.0, 50.0), status='draft'):
    """标准场景：组织树 + 物料 / 单位 / 库位 + 调拨类型 / 序列 + 一张调拨单。

    行 id 从 100 起，行号按 10 递增；行数量依次取 `line_qtys`。
    """
    conn = build_db()
    add_types(conn)
    add_org_tree(conn)
    add_master_data(conn)
    add_transfer_order(conn, oid=1, status=status)
    for index, qty in enumerate(line_qtys):
        add_transfer_line(conn, lid=100 + index, oid=1,
                          line_no=10 * (index + 1), qty=float(qty))
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 需求分配 / 需求行（TBD-4 转调拨）
# ---------------------------------------------------------------------------
def add_requisition_line(conn, lid=500, requisition_id=1, line_no='10',
                         item_id=900, qty=100.0, uom_id=3,
                         need_date='2026-11-10', cost_center_id=None,
                         status='open'):
    conn.execute(
        'INSERT INTO requisition_lines (id, requisition_id, line_no, item_id, '
        'qty, uom_id, need_date, cost_center_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [lid, requisition_id, line_no, item_id, float(qty), uom_id,
         need_date, cost_center_id, status])


def add_allocation(conn, aid=200, demand_line_id=500, qty=100.0,
                   uom_id=3, target_bo='inventory', target_id=0,
                   target_line_id=0, status='active', demand_bo='requisition',
                   demand_id=1, demand_line_no='10', cost_center_id=None,
                   project_id=None):
    """需求分配种子；`target_bo='inventory'` + `target_id=0` = 尚未落载体。"""
    conn.execute(
        'INSERT INTO demand_allocations (id, demand_bo, demand_id, '
        'demand_line_id, demand_line_no, target_bo, target_id, target_line_id, '
        'qty, uom_id, cost_center_id, project_id, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [aid, demand_bo, demand_id, demand_line_id, demand_line_no, target_bo,
         target_id, target_line_id, float(qty), uom_id, cost_center_id,
         project_id, status])


def from_allocation_service(conn, framework=None):
    from meta.services.transfer_order_from_allocation import (
        TransferOrderFromAllocationService)
    return TransferOrderFromAllocationService(MemDS(conn), framework)


# ---------------------------------------------------------------------------
# 服务构造辅助
# ---------------------------------------------------------------------------
def to_service(conn):
    from meta.services.transfer_order_service import TransferOrderService
    return TransferOrderService(MemDS(conn))


def to_guard(conn):
    from meta.services.transfer_order_guard_service import TransferOrderGuardService
    return TransferOrderGuardService(MemDS(conn))


def receipt_svc(conn):
    from meta.services.receipt_service import ReceiptService
    return ReceiptService(MemDS(conn))


def receipt_guard_svc(conn):
    from meta.services.receipt_guard_service import ReceiptGuardService
    return ReceiptGuardService(MemDS(conn))
