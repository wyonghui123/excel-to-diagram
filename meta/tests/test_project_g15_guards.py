# -*- coding: utf-8 -*-
"""G15 ETO 执行守卫（P1-5 / P1-6）验收用例。

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.2 / §4.4 / §5 / §6

口径提醒:
  · 采购行 `purchase_order_line` 不加 project_task_id —— 项目/任务归属只走
    `demand_allocations`（A6 按此替代口径验证）。
  · 收货 / 库存段字段为既有 INV-2（v205）实现，本用例不新增字段。
"""
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services import project_task_guard
from meta.services.inventory_guard_service import InventoryError
from meta.services.inventory_posting_service import InventoryPostingService
from meta.services.purchase_order_guard_service import (
    PurchaseOrderGuardError, PurchaseOrderGuardService,
)
from meta.services.stock_segment_service import (
    DEFAULT_SEGMENT, SEGMENT_OWNED, SEGMENT_PROJECT_TASK,
)
from meta.services.work_order_service import WorkOrderError, WorkOrderService
from meta.tests.inventory_test_doubles import (
    BATCH_ID, ITEM_ID, LOCATION_ID, MemDS, ORG_ID, build_db, seed,
)

_SCHEDULE_ID = 1
_ORDER_ID = 10
_ORDER_LINE_ID = 100

_SCHEMA = """
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    design_mode TEXT
);
CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    parent_task_id INTEGER,
    task_no TEXT,
    name TEXT,
    task_type TEXT,
    status TEXT
);
CREATE TABLE sales_order_schedules (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_id INTEGER,
    schedule_kind TEXT,
    promised_date TEXT,
    status TEXT,
    updated_at TEXT
);
CREATE TABLE sales_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    fulfillment_status TEXT DEFAULT 'not_started',
    updated_at TEXT
);
CREATE TABLE calendars (
    id INTEGER PRIMARY KEY,
    day_mask_mon INTEGER DEFAULT 1,
    day_mask_tue INTEGER DEFAULT 1,
    day_mask_wed INTEGER DEFAULT 1,
    day_mask_thu INTEGER DEFAULT 1,
    day_mask_fri INTEGER DEFAULT 1,
    day_mask_sat INTEGER DEFAULT 0,
    day_mask_sun INTEGER DEFAULT 0
);
CREATE TABLE calendar_days (
    id INTEGER PRIMARY KEY,
    calendar_id INTEGER,
    date TEXT,
    day_type TEXT
);
CREATE TABLE sla_coverages (
    id INTEGER PRIMARY KEY,
    name TEXT,
    org_id INTEGER,
    calendar_id INTEGER,
    start_date TEXT,
    end_date TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE sla_coverage_rules (
    id INTEGER PRIMARY KEY,
    coverage_id INTEGER,
    severity TEXT,
    channel TEXT,
    first_response_minutes INTEGER,
    first_response_warn_minutes INTEGER,
    resolution_minutes INTEGER,
    resolution_warn_minutes INTEGER,
    seq INTEGER DEFAULT 0
);
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_no TEXT,
    order_type TEXT,
    schedule_id INTEGER,
    order_id INTEGER,
    order_line_id INTEGER,
    customer_account_id INTEGER,
    project_id INTEGER,
    project_task_id INTEGER,
    severity TEXT,
    channel TEXT,
    status TEXT,
    coverage_id INTEGER,
    asset_ref TEXT,
    source_demand_type TEXT,
    source_demand_id INTEGER,
    opened_at TEXT,
    first_response_at TEXT,
    resolved_at TEXT,
    closed_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE sla_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER,
    project_id INTEGER,
    milestone_type TEXT,
    state TEXT,
    due_at TEXT,
    warn_at TEXT,
    started_at TEXT,
    paused_total_minutes INTEGER DEFAULT 0,
    completed_at TEXT,
    warned_at TEXT,
    breached_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE service_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER,
    event_type TEXT,
    occurred_at TEXT,
    actor TEXT,
    payload TEXT,
    note TEXT,
    created_at TEXT
);
CREATE TABLE change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT,
    object_id INTEGER,
    event_type TEXT,
    changed_fields TEXT,
    old_values TEXT,
    new_values TEXT,
    payload TEXT,
    status TEXT,
    created_at TEXT
);
CREATE TABLE receipt_lines (
    id INTEGER PRIMARY KEY,
    receipt_id INTEGER,
    project_task_id INTEGER
);
CREATE TABLE inventory_transactions (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    project_task_id INTEGER,
    stock_segment_type TEXT,
    sales_order_line_id INTEGER,
    owner_party_id INTEGER
);
CREATE TABLE purchase_order_lines (
    id INTEGER PRIMARY KEY,
    order_id INTEGER,
    line_type_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty REAL,
    unit_price REAL,
    tax_code_id INTEGER,
    tax_rate_percent REAL,
    tax_recoverable INTEGER,
    parent_line_id INTEGER,
    pricing_mode TEXT,
    header_discount_amount REAL,
    header_surcharge_amount REAL,
    status TEXT
);
CREATE TABLE purchase_order_schedules (
    id INTEGER PRIMARY KEY,
    line_id INTEGER,
    promised_qty REAL
);
CREATE TABLE demand_allocations (
    id INTEGER PRIMARY KEY,
    demand_bo TEXT,
    demand_id INTEGER,
    demand_line_id INTEGER,
    target_bo TEXT,
    target_id INTEGER,
    target_line_id INTEGER,
    target_schedule_id INTEGER,
    qty REAL,
    status TEXT,
    project_id INTEGER,
    project_task_id INTEGER
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


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    conn.execute(
        'INSERT INTO sales_order_schedules (id, order_id, line_id, '
        "schedule_kind, promised_date, status) VALUES (?, ?, ?, 'service', "
        "'2026-11-10', 'planned')",
        [_SCHEDULE_ID, _ORDER_ID, _ORDER_LINE_ID])
    conn.execute(
        'INSERT INTO sales_order_lines (id, order_id, fulfillment_status) '
        "VALUES (?, ?, 'not_started')", [_ORDER_LINE_ID, _ORDER_ID])
    conn.execute(
        'INSERT INTO calendars (id) VALUES (1)')
    return conn


def _add_project(conn, pid, mode):
    conn.execute('INSERT INTO projects (id, design_mode) VALUES (?, ?)',
                 [pid, mode])


def _add_task(conn, tid, pid, task_type='activity', status='planned'):
    conn.execute(
        'INSERT INTO project_tasks (id, project_id, parent_task_id, task_no, '
        'name, task_type, status) VALUES (?, ?, NULL, ?, ?, ?, ?)',
        [tid, pid, 'T%s' % tid, '任务%s' % tid, task_type, status])


def _service_payload(**extra):
    payload = {
        'schedule_id': _SCHEDULE_ID,
        'severity': 'high',
        'opened_at': '2026-11-04 09:00:00',
    }
    payload.update(extra)
    return payload


_CREATE_KW = dict(
    schedule_id=_SCHEDULE_ID,
    severity='high',
)


# ---------------------------------------------------------------- A1 G4


def test_a1_engineered_project_requires_project_task():
    conn = _db()
    _add_project(conn, 1, 'engineered')
    _add_task(conn, 11, 1)
    _add_task(conn, 12, 1)
    svc = WorkOrderService(_MemDS(conn))
    with pytest.raises(WorkOrderError) as exc:
        svc.create_work_order(_service_payload(project_id=1))
    assert exc.value.rule == project_task_guard.RULE_TASK_REQUIRED
    assert exc.value.field_name == 'project_task_id'
    assert 'engineered' in str(exc.value)


# ---------------------------------------------------------------- A2 G2


def test_a2_task_must_belong_to_same_project():
    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_project(conn, 2, 'standard')
    _add_task(conn, 21, 2)
    svc = WorkOrderService(_MemDS(conn))
    with pytest.raises(WorkOrderError) as exc:
        svc.create_work_order(_service_payload(project_id=1,
                                               project_task_id=21))
    assert exc.value.rule == project_task_guard.RULE_PROJECT_MISMATCH
    assert exc.value.field_name == 'project_task_id'


# ---------------------------------------------------------------- A3 G3


def test_a3_task_must_be_executable_activity():
    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_task(conn, 31, 1, status='done')
    _add_task(conn, 32, 1, task_type='phase', status='planned')
    svc = WorkOrderService(_MemDS(conn))
    for task_id in (31, 32):
        with pytest.raises(WorkOrderError) as exc:
            svc.create_work_order(_service_payload(
                project_id=1, project_task_id=task_id))
        assert exc.value.rule == project_task_guard.RULE_NOT_EXECUTABLE


def test_a3_in_progress_activity_is_accepted():
    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_task(conn, 33, 1, status='in_progress')
    svc = WorkOrderService(_MemDS(conn))
    created = svc.create_work_order(_service_payload(
        project_id=1, project_task_id=33))
    row = conn.execute(
        'SELECT project_task_id FROM work_orders WHERE id = ?',
        [created['id']]).fetchone()
    assert row[0] == 33


# ---------------------------------------------------------------- A4 G1


def test_a4_task_requires_project():
    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_task(conn, 41, 1)
    svc = WorkOrderService(_MemDS(conn))
    with pytest.raises(WorkOrderError) as exc:
        svc.create_work_order(_service_payload(project_task_id=41))
    assert exc.value.rule == project_task_guard.RULE_PROJECT_REQUIRED
    assert exc.value.field_name == 'project_id'


# ---------------------------------------------------------------- A5 G5


def test_a5_released_work_order_locks_project_scope():
    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_project(conn, 2, 'standard')
    _add_task(conn, 51, 1)
    _add_task(conn, 52, 2)
    svc = WorkOrderService(_MemDS(conn))
    old = {'id': 900, 'status': 'released', 'project_id': 1,
           'project_task_id': 51}
    with pytest.raises(WorkOrderError) as exc:
        svc.validate_project_scope({'project_task_id': 52}, existing=old)
    assert exc.value.rule == project_task_guard.RULE_TASK_LOCKED
    # 未变更 / 非发布态可继续维护
    assert svc.validate_project_scope(
        {'project_task_id': 51}, existing=old)['project_task_id'] == 51
    assert svc.validate_project_scope(
        {'project_id': 2, 'project_task_id': 52},
        existing=dict(old, status='in_progress'))['project_task_id'] == 52


# ---------------------------------------------------------------- A6 G6


def test_a6_purchase_ownership_is_carried_by_demand_allocation():
    from pathlib import Path

    import yaml

    schemas = Path(__file__).resolve().parents[1] / 'schemas'
    line_spec = yaml.safe_load(
        (schemas / 'purchase_order_line.yaml').read_text(encoding='utf-8'))
    field_ids = {field.get('id') for field in line_spec.get('fields', [])}
    assert 'project_task_id' not in field_ids
    allocation_spec = yaml.safe_load(
        (schemas / 'demand_allocation.yaml').read_text(encoding='utf-8'))
    allocation_fields = {field.get('id')
                         for field in allocation_spec.get('fields', [])}
    assert {'project_id', 'project_task_id'} <= allocation_fields

    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_project(conn, 2, 'standard')
    _add_task(conn, 61, 1)
    _add_task(conn, 62, 2)
    conn.execute('INSERT INTO purchase_order_lines (id, order_id, qty, '
                 'unit_price) VALUES (1, 1, 100, 10)')
    service = PurchaseOrderGuardService(_MemDS(conn))
    bad = {
        'qty': 5, 'demand_bo': 'service_order', 'demand_id': 1,
        'demand_line_id': 1, 'target_bo': 'purchase_order', 'target_id': 1,
        'target_line_id': 1, 'project_id': 1, 'project_task_id': 62,
    }
    with pytest.raises(PurchaseOrderGuardError) as exc:
        service.validate_allocation_write(bad)
    assert exc.value.rule == 'PO_ALLOCATION_TASK_PROJECT_MISMATCH'
    ok = dict(bad, project_task_id=61)
    service.validate_allocation_write(ok)


# ---------------------------------------------------------------- A7 G9


def test_a7_referenced_task_cannot_be_deleted_or_cancelled():
    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_task(conn, 71, 1)
    _add_task(conn, 72, 1)
    conn.execute('INSERT INTO work_orders (work_order_no, project_id, '
                 'project_task_id, status) VALUES (?, ?, ?, ?)',
                 ['WO-1', 1, 71, 'released'])
    ds = _MemDS(conn)
    assert project_task_guard.reference_counts(ds, 71)['工单'] == 1
    with pytest.raises(project_task_guard.ProjectTaskGuardError) as exc:
        project_task_guard.assert_task_not_referenced(ds, 71)
    assert exc.value.status_code == 409
    assert exc.value.rule == project_task_guard.RULE_TASK_REFERENCED
    # 未引用任务允许删除 / 取消
    project_task_guard.assert_task_not_referenced(ds, 72)


# ---------------------------------------------------------------- A8 G8


def _inv_env():
    conn = seed(build_db())
    conn.execute(
        'CREATE TABLE IF NOT EXISTS project_tasks (id INTEGER PRIMARY KEY, '
        'project_id INTEGER, task_type TEXT, status TEXT)')
    conn.execute(
        "INSERT OR IGNORE INTO project_tasks (id, project_id, task_type, "
        "status) VALUES (1, 100, 'activity', 'planned')")
    conn.commit()
    return conn


def _post(conn, segment):
    entry = {
        'transaction_type': 'RCV_PO',
        'transaction_date': '2026-11-04',
        'org_id': ORG_ID, 'location_id': LOCATION_ID,
        'item_id': ITEM_ID, 'uom_id': 3, 'qty': 1, 'batch_id': BATCH_ID,
        'stock_status': 'unrestricted', 'source_line_id': 1,
    }
    entry.update(segment)
    InventoryPostingService(MemDS(conn)).post([entry], {
        'source_doc_type': 'test', 'source_doc_id': 1,
        'source_event_key': 'evt-g8', 'transaction_date': '2026-11-04',
    })


def test_a8_project_task_segment_requires_project_and_task():
    conn = _inv_env()
    with pytest.raises(InventoryError) as exc:
        _post(conn, {'stock_segment_type': SEGMENT_PROJECT_TASK,
                     'project_id': 0, 'project_task_id': 0,
                     'sales_order_line_id': 0, 'owner_party_id': 0})
    assert exc.value.code.startswith('INV_SEGMENT')


def test_a8_owned_segment_rejects_project_partners():
    conn = _inv_env()
    with pytest.raises(InventoryError) as exc:
        _post(conn, {'stock_segment_type': SEGMENT_OWNED,
                     'project_id': 100, 'project_task_id': 1,
                     'sales_order_line_id': 0, 'owner_party_id': 0})
    assert exc.value.code.startswith('INV_SEGMENT')
    # 全 0 伙伴列的 owned 段照常过账
    _post(conn, dict(DEFAULT_SEGMENT, stock_segment_type=SEGMENT_OWNED))


# ---------------------------------------------------------------- A9 G10


def test_a9_projection_exposes_no_write_entry():
    from pathlib import Path

    import yaml

    schemas = Path(__file__).resolve().parents[1] / 'schemas'
    assert not list(schemas.glob('v_project_cost*.yaml'))
    spec = yaml.safe_load(
        (schemas / 'inventory_balance.yaml').read_text(encoding='utf-8'))
    action_ids = [action.get('id') for action in spec.get('actions', [])]
    assert action_ids == ['inventory_balance_read',
                          'inventory_balance_list']
    assert spec.get('import_export', {}).get('auto_crud') is False


# ---------------------------------------------------------------- 迁移


def test_v207_project_task_index_is_idempotent(tmp_path):
    from meta.migrations import v207__project_task_index as migration

    db = tmp_path / 'g15_index.db'
    conn = sqlite3.connect(str(db))
    conn.execute(
        'CREATE TABLE project_tasks (id INTEGER PRIMARY KEY, project_id INTEGER, '
        'status TEXT)')
    conn.commit()
    conn.close()

    assert migration.migrate(db, skip_backup=True) is True
    assert migration.verify(db) is True
    # 重复执行不报错、终态一致
    assert migration.migrate(db, skip_backup=True) is True
    assert migration.verify(db) is True
    # 缺表时幂等跳过（旧库兼容）
    bare = tmp_path / 'bare.db'
    sqlite3.connect(str(bare)).close()
    assert migration.migrate(bare, skip_backup=True) is True


# ---------------------------------------------------------------- A10


def test_a10_standard_project_is_not_subject_to_g4():
    conn = _db()
    _add_project(conn, 1, 'standard')
    _add_task(conn, 101, 1)
    _add_task(conn, 102, 1)
    svc = WorkOrderService(_MemDS(conn))
    created = svc.create_work_order(_service_payload(project_id=1))
    assert created['id']
    row = conn.execute(
        'SELECT project_id, project_task_id FROM work_orders WHERE id = ?',
        [created['id']]).fetchone()
    assert row[0] == 1
    assert row[1] in (None, 0)
