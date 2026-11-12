# -*- coding: utf-8 -*-
"""单据审批规则测试（M3 / spec §6.2.2 R1-R9 / §6.3 / §6.4）

覆盖三块：
  ① `DocumentApprovalResolver` 策略求值（无策略 / 旁路 / 条件 / 优先级 / 生效窗口 / 步骤分段）
  ② `ApprovalTaskService` 建审批待办（标题 / 域 / 快照 / 幂等）
  ③ `purchase_order.approve / .reject` BO Action（状态 + approval_status 正交）
"""

import json
import os
import sqlite3
from types import SimpleNamespace

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services import document_approval_decision
from meta.services.approval_task_service import ApprovalTaskService
from meta.services.document_approval_decision import (
    purchase_order_approve_handler,
    purchase_order_reject_handler,
)
from meta.services.document_approval_service import DocumentApprovalResolver

_SCHEMA = """
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, org_id INTEGER, document_type_id INTEGER,
    status TEXT, approval_status TEXT, gross_amount REAL, net_amount REAL
);
CREATE TABLE approval_policies (
    id INTEGER PRIMARY KEY, code TEXT, name TEXT, scope_bo TEXT,
    trigger_action TEXT, status TEXT, priority INTEGER,
    effective_from TEXT, effective_to TEXT
);
CREATE TABLE approval_policy_conditions (
    id INTEGER PRIMARY KEY, policy_id INTEGER, group_no INTEGER, field_id TEXT,
    operator TEXT, value_number REAL, value_text TEXT, value_json TEXT
);
CREATE TABLE approval_policy_steps (
    id INTEGER PRIMARY KEY, policy_id INTEGER, step_no INTEGER,
    approver_type TEXT, approver_ref TEXT, min_amount REAL, max_amount REAL,
    approve_mode TEXT, sla_hours INTEGER
);
CREATE TABLE control_parameter_defs (
    id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, domain TEXT,
    value_type TEXT, target_bo TEXT, default_value TEXT, description TEXT,
    status TEXT
);
CREATE TABLE control_parameter_values (
    id INTEGER PRIMARY KEY, control_parameter_id INTEGER, org_id INTEGER,
    document_type_id INTEGER, line_type_id INTEGER, item_group_id INTEGER,
    specificity_rank INTEGER, value TEXT, status TEXT, description TEXT
);
CREATE TABLE tasks (
    id TEXT PRIMARY KEY, code TEXT UNIQUE, title TEXT NOT NULL, type TEXT NOT NULL,
    status TEXT NOT NULL, priority TEXT, app_id TEXT, executor_type TEXT NOT NULL,
    assign_policy TEXT, executor_candidates TEXT, executor_config TEXT,
    inputs TEXT, doc_ref TEXT, created_by TEXT, created_at TEXT, attempt INTEGER
);
INSERT INTO control_parameter_defs
    (id, code, name, domain, value_type, target_bo, default_value, status)
VALUES (1, 'approval_enabled', '启用审批', 'procurement', 'bool',
        'purchase_order', 'true', 'active');
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


def _insert_order(conn, order_id=1, gross_amount=12000.0, document_type_id=1,
                  org_id=1, status='draft'):
    conn.execute(
        'INSERT INTO purchase_orders (id, order_no, org_id, document_type_id, '
        'status, approval_status, gross_amount) '
        "VALUES (?, 'PO-202611-000001', ?, ?, ?, 'not_required', ?)",
        [order_id, org_id, document_type_id, status, gross_amount])


def _insert_policy(conn, policy_id=1, code='PO_AMOUNT', scope_bo='purchase_order',
                   trigger_action='submit', status='active', priority=0,
                   effective_from=None, effective_to=None):
    conn.execute(
        'INSERT INTO approval_policies (id, code, name, scope_bo, trigger_action, '
        'status, priority, effective_from, effective_to) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [policy_id, code, code, scope_bo, trigger_action, status, priority,
         effective_from, effective_to])


def _insert_condition(conn, condition_id=1, policy_id=1, field_id='gross_amount',
                      operator='>=', value_number=10000, value_text=None,
                      value_json=None):
    conn.execute(
        'INSERT INTO approval_policy_conditions '
        '(id, policy_id, group_no, field_id, operator, value_number, value_text, '
        'value_json) VALUES (?, ?, 1, ?, ?, ?, ?, ?)',
        [condition_id, policy_id, field_id, operator, value_number,
         value_text, value_json])


def _insert_step(conn, step_id=1, policy_id=1, step_no=1, approver_ref='manager',
                 min_amount=None, max_amount=None):
    conn.execute(
        'INSERT INTO approval_policy_steps (id, policy_id, step_no, approver_type, '
        'approver_ref, min_amount, max_amount, approve_mode, sla_hours) '
        "VALUES (?, ?, ?, 'role', ?, ?, ?, 'any', 24)",
        [step_id, policy_id, step_no, approver_ref, min_amount, max_amount])


# ---------------- 策略求值 ----------------

def test_no_policy_means_not_required(conn, ds):
    _insert_order(conn)
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 1)
    assert result['required'] is False
    assert result['reason'] == 'no_policy'
    assert result['amount'] == 12000.0


def test_record_not_found_is_not_required(ds):
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 999)
    assert result['required'] is False
    assert result['reason'] == 'record_not_found'


def test_invalid_object_rejected(ds):
    result = DocumentApprovalResolver(ds).resolve('unknown_bo', 1)
    assert result['required'] is False
    assert result['reason'] == 'invalid_object'


def test_approval_disabled_by_control_parameter(conn, ds):
    """组织级紧急旁路：approval_enabled=false 直接免审批。"""
    _insert_order(conn)
    _insert_policy(conn)
    conn.execute(
        'INSERT INTO control_parameter_values (id, control_parameter_id, org_id, '
        'specificity_rank, value, status) '
        "VALUES (1, 1, 1, 1, 'false', 'active')")
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 1)
    assert result['required'] is False
    assert result['reason'] == 'disabled'
    assert result['policy_code'] is None


def test_amount_condition_match(conn, ds):
    _insert_order(conn, gross_amount=12000.0)
    _insert_policy(conn)
    _insert_condition(conn, value_number=10000)
    _insert_step(conn)
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 1)
    assert result['required'] is True
    assert result['reason'] == 'matched'
    assert result['policy_code'] == 'PO_AMOUNT'
    assert result['snapshot']['amount'] == 12000.0


def test_amount_condition_miss(conn, ds):
    _insert_order(conn, gross_amount=5000.0)
    _insert_policy(conn)
    _insert_condition(conn, value_number=10000)
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 1)
    assert result['required'] is False
    assert result['reason'] == 'no_policy'


def test_condition_in_operator(conn, ds):
    """多值条件：value_text 逗号分隔 + in。"""
    _insert_order(conn, document_type_id=3, gross_amount=1000.0)
    _insert_policy(conn)
    _insert_condition(conn, field_id='document_type_id', operator='in',
                      value_number=None, value_text='1,3,5')
    _insert_step(conn)
    assert DocumentApprovalResolver(ds).resolve(
        'purchase_order', 1)['required'] is True


def test_condition_between_operator(conn, ds):
    _insert_order(conn, gross_amount=8000.0)
    _insert_policy(conn)
    _insert_condition(conn, operator='between', value_number=None,
                      value_json='[5000, 10000]')
    _insert_step(conn)
    assert DocumentApprovalResolver(ds).resolve(
        'purchase_order', 1)['required'] is True


def test_priority_and_effective_window(conn, ds):
    _insert_order(conn)
    _insert_policy(conn, policy_id=1, code='LOW', priority=5)
    _insert_policy(conn, policy_id=2, code='HIGH', priority=10)
    _insert_step(conn, step_id=1, policy_id=2)
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 1)
    assert result['policy_code'] == 'HIGH'


def test_expired_policy_ignored(conn, ds):
    _insert_order(conn)
    _insert_policy(conn, effective_to='2020-01-01')
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 1)
    assert result['required'] is False
    assert result['reason'] == 'no_policy'


def test_future_policy_ignored(conn, ds):
    _insert_order(conn)
    _insert_policy(conn, effective_from='2030-01-01')
    assert DocumentApprovalResolver(ds).resolve(
        'purchase_order', 1)['required'] is False


def test_cross_object_policy_ignored(conn, ds):
    """E13：scope_bo 不是当前对象的策略不得参与求值。"""
    _insert_order(conn)
    _insert_policy(conn, code='SR_POLICY', scope_bo='service_request')
    assert DocumentApprovalResolver(ds).resolve(
        'purchase_order', 1)['required'] is False


def test_step_amount_band(conn, ds):
    """R5：步骤按金额分段，只返回命中分段的步骤。"""
    _insert_order(conn, gross_amount=8000.0)
    _insert_policy(conn)
    _insert_step(conn, step_id=1, step_no=1, approver_ref='buyer',
                 min_amount=0, max_amount=5000)
    _insert_step(conn, step_id=2, step_no=2, approver_ref='cfo',
                 min_amount=5000, max_amount=None)
    result = DocumentApprovalResolver(ds).resolve('purchase_order', 1)
    assert len(result['steps']) == 1
    assert result['steps'][0]['approver_ref'] == 'cfo'


def test_snapshot_contains_policy_and_conditions(conn, ds):
    _insert_order(conn, gross_amount=12000.0)
    _insert_policy(conn)
    _insert_condition(conn, value_number=10000)
    _insert_step(conn)
    snapshot = DocumentApprovalResolver(ds).resolve(
        'purchase_order', 1)['snapshot']
    assert snapshot['object_type'] == 'purchase_order'
    assert snapshot['trigger_action'] == 'submit'
    assert snapshot['policy_code'] == 'PO_AMOUNT'
    assert snapshot['conditions']
    # M2：审批侧 explain 走统一谓词求值器（field / op / expected / actual / passed）
    assert snapshot['conditions_explain'] == [{
        'field': 'gross_amount',
        'op': 'ge',
        'expected': 10000,
        'actual': 12000.0,
        'passed': True,
    }]
    assert snapshot['steps'][0]['approver_ref'] == 'manager'
    assert snapshot['resolved_at']


# ---------------- 建审批待办 ----------------

def test_create_task_fields(conn, ds):
    _insert_order(conn)
    snapshot = {'policy_code': 'PO_AMOUNT', 'steps': []}
    task_id = ApprovalTaskService(ds).create_task(
        'purchase_order', 1, policy_snapshot=snapshot, actor='tester')
    assert task_id

    row = ds.query('SELECT * FROM tasks WHERE id = ?', [task_id])[0]
    assert row['title'] == '采购订单审批 #PO-202611-000001'
    assert row['type'] == 'approval'
    assert row['status'] == 'waiting_approval'
    assert row['app_id'] == 'procurement'
    assert row['doc_ref'] == '1'
    assert row['created_by'] == 'tester'
    executor = json.loads(row['executor_config'])
    assert executor['decision_actions'] == {
        'approve': 'purchase_order.approve', 'reject': 'purchase_order.reject'}
    inputs = json.loads(row['inputs'])
    assert inputs['purchase_order_id'] == 1
    assert inputs['policy_snapshot'] == snapshot


def test_create_task_idempotent(conn, ds):
    _insert_order(conn)
    service = ApprovalTaskService(ds)
    first = service.create_task('purchase_order', 1)
    assert first
    assert service.create_task('purchase_order', 1) is None


def test_create_task_after_terminal(conn, ds):
    _insert_order(conn)
    service = ApprovalTaskService(ds)
    first = service.create_task('purchase_order', 1)
    ds.execute("UPDATE tasks SET status = 'done' WHERE id = ?", [first])
    second = service.create_task('purchase_order', 1)
    assert second and second != first


def test_create_task_skips_unknown_object(ds):
    assert ApprovalTaskService(ds).create_task('unknown_bo', 1) is None
    assert ApprovalTaskService(ds).create_task('purchase_order', None) is None


# ---------------- BO Action ----------------

def _ok_result():
    return SimpleNamespace(success=True, message='', error=None)


def _patch_ds(monkeypatch, ds):
    monkeypatch.setattr(document_approval_decision, '_get_ds', lambda: ds)


def _patch_update(conn, monkeypatch, apply_change=True):
    def fake_update(record_id, status, approval_status):
        if apply_change:
            conn.execute(
                'UPDATE purchase_orders SET status = ?, approval_status = ? '
                'WHERE id = ?', [status, approval_status, record_id])
        return _ok_result()

    monkeypatch.setattr(document_approval_decision, '_execute_update', fake_update)


def test_approve_moves_to_confirmed(conn, ds, monkeypatch):
    _insert_order(conn, status='submitted')
    conn.execute("UPDATE purchase_orders SET approval_status = 'pending'")
    _patch_ds(monkeypatch, ds)
    _patch_update(conn, monkeypatch)

    result = purchase_order_approve_handler({'purchase_order_id': 1}, {})
    assert result['success'] is True
    assert result['data']['new_status'] == 'confirmed'
    row = ds.query('SELECT status, approval_status FROM purchase_orders WHERE id=1')[0]
    assert row['status'] == 'confirmed'
    assert row['approval_status'] == 'approved'


def test_reject_moves_back_to_draft(conn, ds, monkeypatch):
    _insert_order(conn, status='submitted')
    conn.execute("UPDATE purchase_orders SET approval_status = 'pending'")
    _patch_ds(monkeypatch, ds)
    _patch_update(conn, monkeypatch)

    result = purchase_order_reject_handler({'id': 1}, {})
    assert result['success'] is True
    assert result['data']['new_status'] == 'draft'
    row = ds.query('SELECT status, approval_status FROM purchase_orders WHERE id=1')[0]
    assert row['status'] == 'draft'
    assert row['approval_status'] == 'rejected'


def test_decide_requires_id(conn, ds, monkeypatch):
    _patch_ds(monkeypatch, ds)
    result = purchase_order_approve_handler({}, {})
    assert result['success'] is False
    assert 'purchase_order_id' in result['message']


def test_decide_missing_record(conn, ds, monkeypatch):
    _patch_ds(monkeypatch, ds)
    result = purchase_order_approve_handler({'purchase_order_id': 999}, {})
    assert result['success'] is False
    assert result['code'] == 'NOT_FOUND'


def test_decide_rejects_non_submitted(conn, ds, monkeypatch):
    _insert_order(conn, status='draft')
    _patch_ds(monkeypatch, ds)
    result = purchase_order_approve_handler({'purchase_order_id': 1}, {})
    assert result['success'] is False
    assert result['code'] == 'INVALID_STATUS'


def test_decide_same_status_is_noop_success(conn, ds, monkeypatch):
    _insert_order(conn, status='confirmed')
    _patch_ds(monkeypatch, ds)
    result = purchase_order_approve_handler({'purchase_order_id': 1}, {})
    assert result['success'] is True
    assert result['data']['new_status'] == 'confirmed'


def test_decide_detects_effect_not_applied(conn, ds, monkeypatch):
    """框架对未知动作可能返回 success=True，必须复核落库结果。"""
    _insert_order(conn, status='submitted')
    _patch_ds(monkeypatch, ds)
    _patch_update(conn, monkeypatch, apply_change=False)
    result = purchase_order_approve_handler({'purchase_order_id': 1}, {})
    assert result['success'] is False
    assert result['code'] == 'EFFECT_NOT_APPLIED'
