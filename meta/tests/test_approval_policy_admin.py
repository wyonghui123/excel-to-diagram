# -*- coding: utf-8 -*-
"""审批策略配置服务测试（M3 / spec-approval-workflow §6）

覆盖：
  ① CRUD：新建 version=1；保存 version+1；子表整体替换；
  ② 校验：编码重复 / 未声明审批接入点 / 非法运算符 / OR 逻辑 / 步骤序号重复；
  ③ 试算：preview 与 DocumentApprovalResolver 同 record 结果一致（薄适配）；
  ④ 路由 fail-closed：未登录一律 401（权限真源 = rule_center:read|write）。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
from flask import Flask

pytestmark = pytest.mark.unit

from meta.api.approval_policy_api import approval_policy_bp
from meta.services import approval_policy_admin_service as service
from meta.services.document_approval_service import DocumentApprovalResolver

_SCHEMA = """
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, org_id INTEGER, document_type_id INTEGER,
    status TEXT, approval_status TEXT, gross_amount REAL, net_amount REAL
);
CREATE TABLE approval_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT,
    scope_bo TEXT, trigger_action TEXT, priority INTEGER, status TEXT,
    description TEXT, effective_from TEXT, effective_to TEXT,
    version INTEGER, created_by TEXT, updated_by TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE approval_policy_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, policy_id INTEGER, group_no INTEGER,
    logic TEXT, field_id TEXT, operator TEXT, value_number REAL,
    value_text TEXT, value_json TEXT, created_by TEXT, updated_by TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE approval_policy_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, policy_id INTEGER, step_no INTEGER,
    approver_type TEXT, approver_ref TEXT, min_amount REAL, max_amount REAL,
    approve_mode TEXT, sla_hours INTEGER, created_by TEXT, updated_by TEXT,
    created_at TEXT, updated_at TEXT
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
INSERT INTO control_parameter_defs
    (id, code, name, domain, value_type, target_bo, default_value, status)
VALUES (1, 'approval_enabled', '启用审批', 'procurement', 'bool',
        'purchase_order', 'true', 'active');
INSERT INTO purchase_orders (id, order_no, org_id, document_type_id, status,
                             gross_amount, net_amount)
VALUES (1, 'PO-001', 1, 1, 'draft', 12000.0, 12000.0);
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

    def begin_transaction(self):
        pass

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()


@pytest.fixture
def ds():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    yield _MemDS(conn)
    conn.close()


def _payload(**overrides):
    data = {
        'code': 'po_amount_approval',
        'name': '采购订单金额审批',
        'scope_bo': 'purchase_order',
        'trigger_action': 'submit',
        'priority': 100,
        'status': 'active',
        'conditions': [{'field_id': 'gross_amount', 'operator': 'ge', 'value': 5000}],
        'steps': [{'step_no': 1, 'approver_type': 'role',
                   'approver_ref': 'purchasing_manager', 'approve_mode': 'any'}],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# CRUD / 版本
# ---------------------------------------------------------------------------
def test_create_policy_sets_version_one_and_children(ds):
    saved = service.save_policy(ds, _payload(), actor='tester')

    assert saved['version'] == 1
    assert saved['code'] == 'po_amount_approval'
    assert len(saved['conditions']) == 1
    assert saved['conditions'][0]['field_id'] == 'gross_amount'
    assert saved['conditions'][0]['value_number'] == 5000.0
    assert len(saved['steps']) == 1
    assert saved['created_by'] == 'tester'


def test_update_policy_increments_version_and_replaces_children(ds):
    created = service.save_policy(ds, _payload())

    updated = service.save_policy(
        ds,
        {'priority': 200,
         'conditions': [{'field_id': 'net_amount', 'operator': 'gt', 'value': 8000}],
         'steps': [
             {'step_no': 1, 'approver_ref': 'purchasing_manager'},
             {'step_no': 2, 'approver_ref': 'finance_director'},
         ]},
        policy_id=created['id'], actor='tester')

    assert updated['version'] == 2
    assert updated['priority'] == 200
    assert [row['field_id'] for row in updated['conditions']] == ['net_amount']
    assert [row['step_no'] for row in updated['steps']] == [1, 2]


def test_duplicate_code_rejected(ds):
    service.save_policy(ds, _payload())
    with pytest.raises(ValueError):
        service.save_policy(ds, _payload(name='另一条'))


def test_update_keeps_own_code(ds):
    created = service.save_policy(ds, _payload())
    saved = service.save_policy(ds, {'name': '改名'}, policy_id=created['id'])
    assert saved['version'] == 2
    assert saved['code'] == 'po_amount_approval'


def test_list_policies_returns_summary(ds):
    service.save_policy(ds, _payload())
    page = service.list_policies(ds)
    assert page['total'] == 1
    item = page['items'][0]
    assert item['condition_count'] == 1
    assert item['step_count'] == 1
    assert 'gross_amount' in item['condition_summary']


# ---------------------------------------------------------------------------
# 校验（fail-closed）
# ---------------------------------------------------------------------------
def test_non_approvable_scope_rejected(ds):
    with pytest.raises(ValueError):
        service.save_policy(ds, _payload(scope_bo='sales_order'))


def test_invalid_operator_rejected(ds):
    with pytest.raises(ValueError):
        service.save_policy(ds, _payload(
            conditions=[{'field_id': 'gross_amount', 'operator': 'no_such_op'}]))


def test_or_logic_rejected(ds):
    with pytest.raises(ValueError):
        service.save_policy(ds, _payload(
            conditions=[{'field_id': 'gross_amount', 'operator': 'eq',
                         'value': 1, 'logic': 'or'}]))


def test_duplicate_step_no_rejected(ds):
    with pytest.raises(ValueError):
        service.save_policy(ds, _payload(steps=[
            {'step_no': 1, 'approver_ref': 'a'},
            {'step_no': 1, 'approver_ref': 'b'},
        ]))


def test_step_requires_approver_ref(ds):
    with pytest.raises(ValueError):
        service.save_policy(ds, _payload(steps=[{'step_no': 1}]))


def test_missing_policy_raises_lookup(ds):
    with pytest.raises(LookupError):
        service.save_policy(ds, _payload(), policy_id=999)


# ---------------------------------------------------------------------------
# 试算（薄适配 resolver）
# ---------------------------------------------------------------------------
def test_preview_matches_resolver(ds):
    service.save_policy(ds, _payload())

    preview = service.preview(ds, 'purchase_order', 1)
    expected = DocumentApprovalResolver(ds).resolve('purchase_order', 1)

    assert preview['required'] is True
    assert preview['policy_code'] == expected['policy_code']
    assert preview['amount'] == expected['amount'] == 12000.0
    assert (preview['snapshot']['conditions_explain']
            == expected['snapshot']['conditions_explain'])
    assert ([s['step_no'] for s in preview['steps']]
            == [s['step_no'] for s in expected['steps']])
    assert preview['snapshot']['policy_version'] == 1


def test_preview_no_policy_returns_not_required(ds):
    result = service.preview(ds, 'purchase_order', 1)
    assert result['required'] is False
    assert result['reason'] == 'no_policy'


def test_preview_unknown_object_rejected(ds):
    with pytest.raises(ValueError):
        service.preview(ds, 'sales_order', 1)


# ---------------------------------------------------------------------------
# 路由 fail-closed（未登录不触库）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('method,path', [
    ('get', '/api/v1/approval-policies'),
    ('get', '/api/v1/approval-policies/options'),
    ('get', '/api/v1/approval-policies/preview?object_type=purchase_order&record_id=1'),
    ('get', '/api/v1/approval-policies/1'),
    ('post', '/api/v1/approval-policies'),
    ('put', '/api/v1/approval-policies/1'),
])
def test_routes_require_login(method, path):
    app = Flask(__name__)
    app.register_blueprint(approval_policy_bp)
    response = getattr(app.test_client(), method)(path)
    assert response.status_code == 401