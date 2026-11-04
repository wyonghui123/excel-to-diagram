# -*- coding: utf-8 -*-
"""需求分配行测试（M3 / spec §9 / §9.4）

两部分：
  ① schema 口径断言（读真实 YAML，防漂移）
  ② 守卫不变量（内存 SQLite 真 SQL，断言错误规则码）
"""

import os
import sqlite3
from pathlib import Path

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.services.purchase_order_guard_service import (
    PurchaseOrderGuardError,
    PurchaseOrderGuardService,
)

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'

_SCHEMA = """
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, status TEXT, document_type_id INTEGER,
    purchase_org_id INTEGER, purchase_legal_entity_id INTEGER,
    supplier_party_id INTEGER, currency_id INTEGER,
    exchange_rate REAL, exchange_rate_type TEXT, exchange_rate_date TEXT,
    approval_status TEXT
);
CREATE TABLE purchase_order_lines (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_no TEXT, line_type_id INTEGER,
    item_id INTEGER, uom_id INTEGER, qty REAL, unit_price REAL, tax_code_id INTEGER,
    tax_rate_percent REAL, tax_recoverable INTEGER DEFAULT 1,
    parent_line_id INTEGER, pricing_mode TEXT,
    status TEXT DEFAULT 'open'
);
CREATE TABLE purchase_order_schedules (
    id INTEGER PRIMARY KEY, order_id INTEGER, line_id INTEGER, schedule_no INTEGER,
    schedule_kind TEXT DEFAULT 'delivery', promised_date TEXT, promised_qty REAL,
    received_qty REAL, status TEXT DEFAULT 'planned'
);
CREATE TABLE demand_allocations (
    id INTEGER PRIMARY KEY, demand_bo TEXT, demand_id INTEGER, demand_line_id INTEGER,
    demand_line_no TEXT, demand_need_date TEXT, project_id INTEGER,
    project_task_id INTEGER, target_bo TEXT, target_id INTEGER,
    target_line_id INTEGER, target_schedule_id INTEGER, qty REAL, uom_id INTEGER,
    allocated_amount REAL, cost_center_id INTEGER, expense_account_code TEXT,
    asset_category_code TEXT, charge_basis TEXT, status TEXT, reversed_at TEXT
);
CREATE TABLE requisition_lines (
    id INTEGER PRIMARY KEY, requisition_id INTEGER, line_no TEXT, qty REAL
);
CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY, project_id INTEGER, task_no TEXT, name TEXT,
    task_type TEXT, status TEXT, parent_task_id INTEGER
);
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


# ---------------- schema 口径 ----------------

def _load(name):
    return yaml.safe_load((_SCHEMA_DIR / name).read_text(encoding='utf-8'))


def test_schema_file_and_shape():
    schema = _load('demand_allocation.yaml')
    assert schema['id'] == 'demand_allocation'
    assert schema['table_name'] == 'demand_allocations'
    # 多态表：不声明 parent_object，不进任何对象 child_sections
    assert 'parent_object' not in schema
    assert schema['ui_view_config']['skip_auto_menu'] is True
    assert schema['audit']['enabled'] is True


def test_required_fields():
    fields = {f['id']: f for f in _load('demand_allocation.yaml')['fields']}
    for field_id in ('demand_bo', 'demand_id', 'demand_line_id',
                     'target_bo', 'target_id', 'target_line_id', 'qty'):
        assert fields[field_id]['required'] is True, field_id
    assert fields['charge_basis']['default'] == 'inventory'
    assert fields['status']['default'] == 'active'


def test_enum_values():
    fields = {f['id']: f for f in _load('demand_allocation.yaml')['fields']}
    demand_bos = {v['value'] for v in fields['demand_bo']['enum_values']}
    assert demand_bos == {'requisition', 'service_request',
                          'sales_order_schedule', 'project_task'}
    target_bos = {v['value'] for v in fields['target_bo']['enum_values']}
    assert target_bos == {'purchase_order', 'receipt', 'transfer_order',
                          'work_order', 'sales_order'}
    charge = {v['value'] for v in fields['charge_basis']['enum_values']}
    assert charge == {'inventory', 'project', 'expense', 'asset'}
    assert {v['value'] for v in fields['status']['enum_values']} == {
        'active', 'reversed'}


def test_readonly_cache_fields():
    fields = {f['id']: f for f in _load('demand_allocation.yaml')['fields']}
    for field_id in ('allocated_amount', 'demand_line_no', 'demand_need_date',
                     'reversed_at'):
        assert fields[field_id].get('ui', {}).get('editable') is False or \
            fields[field_id].get('ui', {}).get('readonly') is True, field_id


def test_qty_constraint():
    fields = {f['id']: f for f in _load('demand_allocation.yaml')['fields']}
    constraint = fields['qty']['constraints'][0]
    assert constraint['type'] == 'numeric_range'
    assert constraint['gt'] == 0


def test_partial_unique_indexes():
    """SQLite 唯一索引对 NULL 不去重 → 拆两条 partial 唯一索引。"""
    indexes = _load('demand_allocation.yaml')['indexes']
    unique = [i for i in indexes if i.get('unique')]
    assert len(unique) == 2
    conditions = {i['name']: i.get('condition') for i in unique}
    assert conditions['uidx_demand_alloc_target'] == 'target_schedule_id IS NULL'
    assert conditions['uidx_demand_alloc_target_schedule'] == \
        'target_schedule_id IS NOT NULL'


def test_no_project_task_on_purchase_order_line():
    """T-D3：项目任务只允许落在分配行，不允许落在 PO 行。"""
    line_fields = {f['id'] for f in _load('purchase_order_line.yaml')['fields']}
    assert 'project_task_id' not in line_fields


# ---------------- 守卫 ----------------

def _insert_order(conn):
    conn.execute(
        "INSERT INTO purchase_orders (id, order_no, status) "
        "VALUES (1, 'PO-001', 'draft')")


def _insert_line(conn, line_id=10, qty=10.0):
    conn.execute(
        'INSERT INTO purchase_order_lines (id, order_id, line_no, line_type_id, '
        'item_id, uom_id, qty, pricing_mode) '
        "VALUES (?, 1, '10', 111, 100, 1, ?, 'standalone')",
        [line_id, qty])


def _insert_task(conn, task_id=21, project_id=7,
                 task_type='activity', status='planned'):
    conn.execute(
        'INSERT INTO project_tasks (id, project_id, task_no, name, task_type, status) '
        "VALUES (?, ?, 'T21', '任务', ?, ?)",
        [task_id, project_id, task_type, status])


def _alloc(**overrides):
    row = {
        'id': None, 'demand_bo': 'requisition', 'demand_id': 1,
        'demand_line_id': 2, 'target_bo': 'purchase_order', 'target_id': 1,
        'target_line_id': 10, 'target_schedule_id': None, 'qty': 1.0,
        'charge_basis': 'inventory', 'status': 'active',
    }
    row.update(overrides)
    return row


def test_allocation_qty_must_be_positive(ds):
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(qty=0), is_create=True), 'PO_ALLOCATION_QTY_POSITIVE')


def test_allocation_required_fields(ds):
    guard = PurchaseOrderGuardService(ds)
    for field in ('demand_bo', 'demand_id', 'demand_line_id',
                  'target_bo', 'target_id', 'target_line_id'):
        _expect_rule(lambda f=field: guard.validate_allocation_write(
            _alloc(**{f: None}), is_create=True),
            'PO_ALLOCATION_REQUIRED_MISSING')


def test_allocation_target_bo_limited_to_m3(conn, ds):
    """M3 只允许 purchase_order / transfer_order / work_order 三种载体。"""
    _insert_order(conn)
    _insert_line(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(target_bo='receipt'), is_create=True),
        'PO_ALLOCATION_TARGET_INVALID')


def test_charge_basis_linkage(conn, ds):
    _insert_order(conn)
    _insert_line(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(charge_basis='project'), is_create=True),
        'PO_ALLOCATION_PROJECT_REQUIRED')
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(charge_basis='expense'), is_create=True),
        'PO_ALLOCATION_EXPENSE_ACCOUNT_REQUIRED')
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(charge_basis='asset'), is_create=True),
        'PO_ALLOCATION_ASSET_CATEGORY_REQUIRED')
    guard.validate_allocation_write(
        _alloc(charge_basis='project', project_id=7), is_create=True)
    guard.validate_allocation_write(
        _alloc(charge_basis='expense', expense_account_code='6602'), is_create=True)
    guard.validate_allocation_write(
        _alloc(charge_basis='asset', asset_category_code='FA01'), is_create=True)


def test_allocation_task_requires_project(conn, ds):
    """G1：填任务必须同时填项目。"""
    _insert_order(conn)
    _insert_line(conn)
    _insert_task(conn)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(project_task_id=21), is_create=True),
        'PO_ALLOCATION_TASK_PROJECT_REQUIRED')


def test_allocation_task_must_belong_to_project(conn, ds):
    """G2：任务必须存在且属于同一项目。"""
    _insert_order(conn)
    _insert_line(conn)
    _insert_task(conn, project_id=8)
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(charge_basis='project', project_id=7, project_task_id=21),
        is_create=True), 'PO_ALLOCATION_TASK_PROJECT_MISMATCH')
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(charge_basis='project', project_id=7, project_task_id=99),
        is_create=True), 'PO_ALLOCATION_TASK_NOT_FOUND')


def test_allocation_task_must_be_executable_activity(conn, ds):
    """G3：任务类型 activity 且状态 planned/in_progress。"""
    _insert_order(conn)
    _insert_line(conn)
    _insert_task(conn, task_type='phase')
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(charge_basis='project', project_id=7, project_task_id=21),
        is_create=True), 'PO_ALLOCATION_TASK_TYPE_INVALID')
    conn.execute(
        "UPDATE project_tasks SET task_type='activity', status='done' WHERE id=21")
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(charge_basis='project', project_id=7, project_task_id=21),
        is_create=True), 'PO_ALLOCATION_TASK_STATUS_INVALID')
    conn.execute("UPDATE project_tasks SET status='in_progress' WHERE id=21")
    guard.validate_allocation_write(
        _alloc(charge_basis='project', project_id=7, project_task_id=21),
        is_create=True)


def test_allocation_line_cap(conn, ds):
    _insert_order(conn)
    _insert_line(conn, qty=10)
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 10, 6, 'active')")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(qty=5), is_create=True), 'PO_ALLOCATION_LINE_CAP_EXCEEDED')


def test_allocation_schedule_must_match_line(conn, ds):
    _insert_order(conn)
    _insert_line(conn)
    conn.execute(
        'INSERT INTO purchase_order_schedules (id, order_id, line_id, schedule_no, '
        'promised_date, promised_qty, status) '
        "VALUES (5, 1, 11, 1, '2026-11-10', 5, 'planned')")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(target_schedule_id=5), is_create=True),
        'PO_ALLOCATION_SCHEDULE_MISMATCH')


def test_allocation_schedule_cap(conn, ds):
    _insert_order(conn)
    _insert_line(conn)
    conn.execute(
        'INSERT INTO purchase_order_schedules (id, order_id, line_id, schedule_no, '
        'promised_date, promised_qty, status) '
        "VALUES (5, 1, 10, 1, '2026-11-10', 5, 'planned')")
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, target_schedule_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 10, 5, 3, 'active')")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(target_schedule_id=5, qty=3), is_create=True),
        'PO_ALLOCATION_SCHEDULE_CAP_EXCEEDED')


def test_allocation_demand_cap(conn, ds):
    _insert_order(conn)
    _insert_line(conn)
    conn.execute(
        "INSERT INTO requisition_lines (id, requisition_id, line_no, qty) "
        "VALUES (2, 1, '10', 4)")
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 10, 2, 'active')")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_write(
        _alloc(qty=3), is_create=True), 'PO_ALLOCATION_DEMAND_CAP_EXCEEDED')


def test_reverse_writes_reversed_at(conn, ds):
    """守卫只在写入参数里补 reversed_at（落库由持久化拦截器按 params 执行）。"""
    _insert_order(conn)
    _insert_line(conn)
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 10, 1, 'active')")
    guard = PurchaseOrderGuardService(ds)
    old = _alloc(id=1, qty=1)
    data = dict(old, status='reversed')
    guard.validate_allocation_write(data, old_data=old, is_create=False)
    assert data['status'] == 'reversed'
    assert data['reversed_at']


def test_delete_only_active(conn, ds):
    conn.execute(
        "INSERT INTO demand_allocations (id, demand_bo, demand_id, demand_line_id, "
        "target_bo, target_id, target_line_id, qty, status) "
        "VALUES (1, 'requisition', 1, 2, 'purchase_order', 1, 10, 1, 'reversed')")
    guard = PurchaseOrderGuardService(ds)
    _expect_rule(lambda: guard.validate_allocation_delete(1),
                 'PO_ALLOCATION_DELETE_NOT_ACTIVE')
