# -*- coding: utf-8 -*-
"""采购订单守卫不变量测试（M3 / spec §14 步骤 15 / §14.1 R-PO-0 ~ R-PO-18）

测试策略：内存 SQLite 真 SQL，逐条不变量断言错误规则码（rule），
不依赖 HTTP / 拦截器链。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.purchase_order_guard_service import (
    PurchaseOrderGuardError,
    PurchaseOrderGuardService,
)

_SCHEMA = """
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY, code TEXT, name TEXT, scope_bo TEXT, level TEXT,
    status TEXT, document_category TEXT, line_category TEXT,
    default_type_id INTEGER, number_sequence_id INTEGER
);
CREATE TABLE party_relations (
    id INTEGER PRIMARY KEY, party1_id INTEGER, party2_id INTEGER,
    role TEXT, status TEXT, internal_mark TEXT
);
CREATE TABLE org_functions (
    id INTEGER PRIMARY KEY, org_id INTEGER, function_type TEXT
);
CREATE TABLE orgs (
    id INTEGER PRIMARY KEY, parent_id INTEGER, status TEXT
);
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, status TEXT, document_type_id INTEGER,
    org_id INTEGER, purchase_org_id INTEGER, purchase_legal_entity_id INTEGER,
    supplier_party_id INTEGER, currency_id INTEGER,
    exchange_rate REAL, exchange_rate_type TEXT, exchange_rate_date TEXT,
    approval_status TEXT, net_amount REAL, tax_amount REAL, gross_amount REAL,
    project_id INTEGER
);
CREATE TABLE purchase_order_lines (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_no TEXT, line_type_id INTEGER,
    item_id INTEGER, uom_id INTEGER, qty REAL, unit_price REAL, tax_code_id INTEGER,
    tax_rate_percent REAL, tax_recoverable INTEGER DEFAULT 1,
    parent_line_id INTEGER, pricing_mode TEXT, source_structure_id INTEGER,
    source_structure_line_id INTEGER, component_issue_required INTEGER DEFAULT 0,
    price_source TEXT, price_trace TEXT, status TEXT DEFAULT 'open'
);
CREATE TABLE purchase_order_schedules (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_id INTEGER, schedule_no INTEGER,
    schedule_kind TEXT, promised_date TEXT, promised_qty REAL, status TEXT
);
CREATE TABLE demand_allocations (
    id INTEGER PRIMARY KEY, demand_bo TEXT, demand_id INTEGER, demand_line_id INTEGER,
    target_bo TEXT, target_id INTEGER, target_line_id INTEGER,
    target_schedule_id INTEGER, qty REAL, status TEXT, reversed_at TEXT,
    project_id INTEGER, project_task_id INTEGER, charge_basis TEXT
);
CREATE TABLE item_structure_lines (
    id INTEGER PRIMARY KEY, structure_id INTEGER, item_id INTEGER,
    uom_id INTEGER, line_no TEXT
);
CREATE TABLE requisition_lines (
    id INTEGER PRIMARY KEY, qty REAL
);
INSERT INTO requisition_lines VALUES (2, 10);
INSERT INTO type_definitions VALUES
    (1, 'PO_STD', '标准采购订单', 'purchase_order', 'header', 'active', 'standard', NULL, 116, 3),
    (2, 'SO_STD', '标准销售订单', 'sales_order', 'header', 'active', 'standard', NULL, NULL, NULL),
    (111, 'PO_GOODS', '物料行', 'purchase_order', 'line', 'active', NULL, 'material', 116, NULL),
    (112, 'PO_TEXT', '文本行', 'purchase_order', 'line', 'active', NULL, 'text', 116, NULL),
    (113, 'PO_SUBCONTRACT', '委外行', 'purchase_order', 'line', 'active', NULL, 'subcontract', 116, NULL),
    (114, 'SO_GOODS', '销售物料行', 'sales_order', 'line', 'active', NULL, 'material', NULL, NULL);
INSERT INTO party_relations VALUES (1, 1, 10, 'vendor', 'active', '外部');
INSERT INTO org_functions VALUES
    (1, 1, 'purchasing'), (2, 1, 'legal_entity'),
    (3, 2, 'legal_entity'), (4, 2, 'purchasing');
INSERT INTO orgs VALUES
    (1, NULL, 'active'), (2, NULL, 'active'),
    (10, 1, 'active'), (20, 2, 'active');
"""


class _MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:')
    connection.executescript(_SCHEMA)
    yield connection
    connection.close()


@pytest.fixture
def ds(conn):
    return _MemDS(conn)


def _expect_rule(call, rule):
    with pytest.raises(PurchaseOrderGuardError) as caught:
        call()
    assert caught.value.rule == rule


def _order(**overrides):
    row = {
        'id': 1, 'order_no': 'PO-202611-000001', 'status': 'draft',
        'document_type_id': 1, 'org_id': 1, 'purchase_org_id': 1,
        'supplier_party_id': 10,
        'currency_id': 1, 'exchange_rate': 1, 'exchange_rate_type': 'spot',
        'exchange_rate_date': None, 'approval_status': 'not_required',
        'net_amount': 0, 'tax_amount': 0, 'gross_amount': 0,
    }
    row.update(overrides)
    return row


def _insert_order(conn, **overrides):
    row = _order(**overrides)
    conn.execute(
        'INSERT INTO purchase_orders ({0}) VALUES ({1})'.format(
            ', '.join(row.keys()), ', '.join('?' * len(row))),
        list(row.values()))


# ---------------- 头 ----------------

def test_create_requires_order_no(ds):
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_order_write(
        _order(order_no=None), is_create=True), 'PO_ORDER_NO_MISSING')


def test_create_requires_document_type(ds):
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_order_write(
        _order(document_type_id=None), is_create=True), 'PO_DOCUMENT_TYPE_REQUIRED')


def test_create_rejects_header_type_other_scope(ds):
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_order_write(
        _order(document_type_id=2), is_create=True), 'PO_TYPE_SCOPE_MISMATCH')


def test_create_requires_supplier_org_currency(ds):
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_order_write(
        _order(supplier_party_id=None), is_create=True), 'PO_REQUIRED_MISSING')


def test_exchange_rate_needs_date_when_not_one(ds):
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_order_write(
        _order(exchange_rate=7.2), is_create=True),
        'PO_EXCHANGE_RATE_DATE_REQUIRED')


def test_order_no_is_immutable(conn, ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order()
    _expect_rule(lambda: guard.validate_order_write(
        dict(old, order_no='PO-OTHER'), old_data=old), 'PO_ORDER_NO_IMMUTABLE')


def test_key_fields_immutable_after_draft(conn, ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order(status='submitted')
    _expect_rule(lambda: guard.validate_order_write(
        dict(old, currency_id=2), old_data=old), 'PO_FIELD_IMMUTABLE')


def test_exchange_rate_frozen_after_confirm(conn, ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order(status='confirmed')
    _expect_rule(lambda: guard.validate_order_write(
        dict(old, exchange_rate=7.2, exchange_rate_date='2026-11-01'),
        old_data=old), 'PO_FROZEN_AFTER_CONFIRM')


def test_invalid_status_transition(conn, ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order()
    _expect_rule(lambda: guard.validate_order_write(
        dict(old, status='confirmed'), old_data=old),
        'PO_STATUS_TRANSITION_INVALID')


def test_confirm_blocked_when_approval_pending(conn, ds):
    """R-PO-12：approval_status=pending 时禁止 confirm。"""
    guard = PurchaseOrderGuardService(ds)
    old = _order(status='submitted', approval_status='pending')
    _expect_rule(lambda: guard.validate_order_write(
        dict(old, status='confirmed'), old_data=old), 'PO_APPROVAL_PENDING')


def test_submit_requires_vendor_relation(conn, ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order(supplier_party_id=99)
    _expect_rule(lambda: guard.validate_order_write(
        dict(old, status='submitted'), old_data=old),
        'PO_SUPPLIER_VENDOR_RELATION_MISSING')


def test_submit_requires_purchasing_org(conn, ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order(purchase_org_id=9)
    _expect_rule(lambda: guard.validate_order_write(
        dict(old, status='submitted'), old_data=old),
        'PO_PURCHASE_ORG_FUNCTION_MISSING')


def test_delete_only_draft(conn, ds):
    _insert_order(conn, status='submitted')
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_order_delete(1), 'PO_DELETE_ONLY_DRAFT')


# ---------------- 采购法人快照（TBD-10） ----------------

def test_create_derives_purchase_legal_entity(ds):
    guard = PurchaseOrderGuardService(ds)
    data = _order(purchase_org_id=10)
    guard.validate_order_write(data, is_create=True)
    assert data['purchase_legal_entity_id'] == 1


def test_create_leaves_snapshot_empty_when_unresolved(ds):
    guard = PurchaseOrderGuardService(ds)
    data = _order(purchase_org_id=999)
    guard.validate_order_write(data, is_create=True)
    assert data['purchase_legal_entity_id'] is None


def test_update_recomputes_snapshot_when_purchase_org_changes(ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order(purchase_org_id=1, purchase_legal_entity_id=1)
    data = dict(old, purchase_org_id=20)
    guard.validate_order_write(data, old_data=old)
    assert data['purchase_legal_entity_id'] == 2


def test_update_keeps_snapshot_when_purchase_org_unchanged(ds):
    guard = PurchaseOrderGuardService(ds)
    old = _order(purchase_org_id=20, purchase_legal_entity_id=2)
    data = dict(old, org_id=2)
    guard.validate_order_write(data, old_data=old)
    assert data['purchase_legal_entity_id'] == 2


# ---------------- 行 ----------------

def _line(**overrides):
    row = {
        'id': None, 'order_id': 1, 'line_no': '10', 'line_type_id': 111,
        'item_id': 100, 'uom_id': 1, 'qty': 2, 'unit_price': 10,
        'tax_code_id': 1, 'tax_rate_percent': 13, 'tax_recoverable': 1,
        'parent_line_id': None, 'pricing_mode': 'standalone',
        'source_structure_id': None, 'source_structure_line_id': None,
        'component_issue_required': 0, 'price_source': 'manual',
        'price_trace': None, 'status': 'open',
    }
    row.update(overrides)
    return row


def test_line_qty_must_be_positive(conn, ds):
    _insert_order(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(qty=0), is_create=True), 'PO_LINE_QTY_POSITIVE')


def test_material_line_requires_item_and_uom(conn, ds):
    _insert_order(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(item_id=None), is_create=True), 'PO_LINE_ITEM_REQUIRED')
    _expect_rule(lambda: guard.validate_line_write(
        _line(uom_id=None), is_create=True), 'PO_LINE_UOM_REQUIRED')


def test_non_material_line_requires_description(conn, ds):
    _insert_order(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(line_type_id=112, item_id=None, uom_id=None, description=None),
        is_create=True), 'PO_LINE_DESCRIPTION_REQUIRED')


def test_line_type_must_belong_to_purchase_order(conn, ds):
    _insert_order(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(line_type_id=114), is_create=True), 'PO_TYPE_SCOPE_MISMATCH')


def test_line_create_only_draft_order(conn, ds):
    _insert_order(conn, status='submitted')
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(), is_create=True), 'PO_LINE_ONLY_DRAFT')


def test_bundle_parent_constraints(conn, ds):
    _insert_order(conn)
    _insert_order(conn, id=2)
    conn.execute(
        "INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id, "
        "item_id, uom_id, qty, pricing_mode, parent_line_id) "
        "VALUES (10, 2, '10', 111, 100, 1, 5, 'bundle_price', NULL)")
    conn.execute(
        "INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id, "
        "item_id, uom_id, qty, pricing_mode, parent_line_id) "
        "VALUES (11, 1, '10', 111, 100, 1, 3, 'standalone', NULL)")
    conn.execute(
        "INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id, "
        "item_id, uom_id, qty, pricing_mode, parent_line_id) "
        "VALUES (12, 1, '20', 111, 100, 1, 5, 'bundle_price', NULL)")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(parent_line_id=99), is_create=True), 'PO_BUNDLE_PARENT_NOT_FOUND')
    _expect_rule(lambda: guard.validate_line_write(
        _line(parent_line_id=10), is_create=True), 'PO_BUNDLE_PARENT_OTHER_ORDER')
    _expect_rule(lambda: guard.validate_line_write(
        _line(parent_line_id=11), is_create=True), 'PO_BUNDLE_PARENT_MODE')
    _expect_rule(lambda: guard.validate_line_write(
        _line(parent_line_id=12, qty=6), is_create=True),
        'PO_BUNDLE_CHILD_QTY_EXCEEDED')
    # 父行不得再有父（只允许两级）
    conn.execute('UPDATE purchase_order_lines SET parent_line_id = 11 WHERE id = 12')
    _expect_rule(lambda: guard.validate_line_write(
        _line(parent_line_id=12), is_create=True), 'PO_BUNDLE_PARENT_NESTED')


def test_component_issue_only_subcontract(conn, ds):
    _insert_order(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(component_issue_required=1), is_create=True),
        'PO_COMPONENT_ISSUE_ONLY_SUBCONTRACT')
    guard.validate_line_write(
        _line(line_type_id=113, component_issue_required=1), is_create=True)


def test_non_recoverable_tax_requires_tax_code(conn, ds):
    _insert_order(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(tax_recoverable=0, tax_code_id=None), is_create=True),
        'PO_TAX_CODE_REQUIRED')


def test_price_source_requires_trace(conn, ds):
    _insert_order(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(price_source='agreement', price_trace=None), is_create=True),
        'PO_PRICE_TRACE_REQUIRED')


def test_source_structure_must_match_item(conn, ds):
    _insert_order(conn)
    conn.execute(
        "INSERT INTO item_structure_lines (id, structure_id, item_id, uom_id, line_no) "
        "VALUES (1, 5, 999, 1, '10')")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_write(
        _line(source_structure_line_id=1), is_create=True),
        'PO_SOURCE_STRUCTURE_ITEM_MISMATCH')


def test_line_delete_only_draft_and_no_active_allocation(conn, ds):
    _insert_order(conn, status='submitted')
    conn.execute(
        "INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id) "
        "VALUES (20, 1, '10', 111)")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_line_delete(20), 'PO_LINE_DELETE_ONLY_DRAFT')
    conn.execute("UPDATE purchase_orders SET status='draft' WHERE id=1")
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 20, 1, 'active')")
    _expect_rule(lambda: guard.validate_line_delete(20),
                 'PO_LINE_HAS_ACTIVE_ALLOCATION')


def test_cancelled_line_reverses_allocations(conn, ds):
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, qty, status) "
        "VALUES (2, 'requisition', 1, 2, 'purchase_order', 1, 20, 1, 'active')")
    guard = PurchaseOrderGuardService(ds)
    count = guard.cascade_cancel_line(20)
    assert count == 1
    row = ds.query('SELECT status, reversed_at FROM demand_allocations WHERE id=2')[0]
    assert row['status'] == 'reversed'
    assert row['reversed_at']


# ---------------- 分配 / 项目任务轴（G15 G6） ----------------

def test_allocation_project_must_match_order(conn, ds):
    _insert_order(conn)
    conn.execute('UPDATE purchase_orders SET project_id = 7 WHERE id = 1')
    conn.execute(
        "INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id, qty) "
        "VALUES (20, 1, '10', 111, 5)")
    guard = PurchaseOrderGuardService(ds)
    data = {
        'demand_bo': 'requisition', 'demand_id': 1, 'demand_line_id': 2,
        'target_bo': 'purchase_order', 'target_id': 1, 'target_line_id': 20,
        'qty': 1, 'project_id': 8, 'charge_basis': 'project',
    }
    _expect_rule(lambda: guard.validate_allocation_write(dict(data), is_create=True),
                 'PO_ALLOCATION_PROJECT_MISMATCH')
    data['project_id'] = 7
    guard.validate_allocation_write(dict(data), is_create=True)


def test_allocation_project_allowed_when_order_has_none(conn, ds):
    _insert_order(conn)
    conn.execute(
        "INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id, qty) "
        "VALUES (20, 1, '10', 111, 5)")
    guard = PurchaseOrderGuardService(ds)
    guard.validate_allocation_write({
        'demand_bo': 'requisition', 'demand_id': 1, 'demand_line_id': 2,
        'target_bo': 'purchase_order', 'target_id': 1, 'target_line_id': 20,
        'qty': 1, 'project_id': 7, 'charge_basis': 'project',
    }, is_create=True)
