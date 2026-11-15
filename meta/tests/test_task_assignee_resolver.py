# -*- coding: utf-8 -*-
"""通用任务取人器测试（M5-2 / spec §9.5）

覆盖：user / role / group / org(descendants) / position / job_level /
manager / manager_chain（levels + min_job_level + top_worker_id）/
position_hierarchy / expression / initiator_choice；空池原因；
汇报线一次批量拉取（无 N+1）；建任务写入 assign_explain / stage_no。
"""

import json
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core import task_assignee_resolver as resolver
from meta.services.approval_task_service import ApprovalTaskService

_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY, username TEXT UNIQUE, status TEXT DEFAULT 'active'
);
CREATE TABLE permission_sets (id INTEGER PRIMARY KEY, code TEXT UNIQUE);
CREATE TABLE user_permission_sets (
    id INTEGER PRIMARY KEY, user_id INTEGER, permission_set_id INTEGER
);
CREATE TABLE orgs (
    id INTEGER PRIMARY KEY, code TEXT, parent_id INTEGER, status TEXT DEFAULT 'active'
);
CREATE TABLE org_members (id INTEGER PRIMARY KEY, org_id INTEGER, user_id INTEGER);
CREATE TABLE employees (
    id INTEGER PRIMARY KEY, user_id INTEGER, manager_employee_id INTEGER,
    job_grade TEXT, position TEXT, org_id INTEGER, status TEXT DEFAULT 'active'
);
"""

_TASK_SCHEMA = """
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY, order_no TEXT, org_id INTEGER, document_type_id INTEGER,
    status TEXT, approval_status TEXT, gross_amount REAL
);
CREATE TABLE tasks (
    id TEXT PRIMARY KEY, code TEXT UNIQUE, title TEXT NOT NULL, type TEXT NOT NULL,
    status TEXT NOT NULL, priority TEXT, app_id TEXT, executor_type TEXT NOT NULL,
    assign_policy TEXT, executor_candidates TEXT, executor_config TEXT,
    inputs TEXT, doc_ref TEXT, doc_ref_type TEXT, doc_ref_id TEXT,
    created_by TEXT, created_at TEXT, attempt INTEGER, stage_no INTEGER
);
"""


class _DS:
    def __init__(self, conn):
        self.conn = conn
        self.queries = []

    def query(self, sql, params=None):
        self.queries.append(sql)
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:')
    connection.executescript(_SCHEMA)
    _seed(connection)
    yield connection
    connection.close()


@pytest.fixture
def ds(conn):
    return _DS(conn)


def _seed(connection):
    users = [(1, 'alice'), (2, 'bob'), (3, 'carol'), (4, 'dave'), (5, 'erin')]
    connection.executemany('INSERT INTO users (id, username) VALUES (?, ?)', users)
    connection.executemany(
        'INSERT INTO orgs (id, code, parent_id) VALUES (?, ?, ?)',
        [(1, 'HQ', None), (2, 'SALES', 1), (3, 'SALES_EAST', 2), (4, 'HR', 1)])
    connection.executemany(
        'INSERT INTO org_members (id, org_id, user_id) VALUES (?, ?, ?)',
        [(1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4)])
    connection.executemany(
        'INSERT INTO permission_sets (id, code) VALUES (?, ?)',
        [(10, 'APPROVER'), (11, 'MANAGER')])
    connection.executemany(
        'INSERT INTO user_permission_sets (id, user_id, permission_set_id) '
        'VALUES (?, ?, ?)', [(1, 1, 10), (2, 2, 11)])
    # e1 alice → e2 bob → e3 carol → e4 dave（到顶）；e5 erin 挂在 bob 下
    connection.executemany(
        'INSERT INTO employees (id, user_id, manager_employee_id, job_grade, '
        'position, org_id) VALUES (?, ?, ?, ?, ?, ?)',
        [(1, 1, 2, '5', 'Clerk', 1), (2, 2, 3, '7', 'Buyer', 2),
         (3, 3, 4, '9', 'Manager', 3), (4, 4, None, '10', 'Director', 1),
         (5, 5, 2, '6', 'Buyer', 2)])


def _ctx(ds, initiator='alice'):
    return {'data_source': ds, 'initiator': initiator,
            'record_id': 1, 'object_type': 'purchase_order'}


def _step(approver_type, ref=None, routing=None):
    return {'approver_type': approver_type, 'approver_ref': ref,
            'routing_json': json.dumps(routing) if routing else None}


# ───────────────────────── 基础算子 ─────────────────────────

def test_user_type_keeps_literal_refs(ds):
    result = resolver.resolve(_step('user', 'alice,bob'), _ctx(ds))
    assert result.candidates == ['alice', 'bob']
    assert result.reason is None
    assert result.source == 'approver_ref'


def test_user_type_empty_pool_reason(ds):
    result = resolver.resolve(_step('user', ''), _ctx(ds))
    assert result.candidates == []
    assert result.reason == resolver.REASON_NO_MEMBER


def test_role_expands_via_permission_sets(ds):
    result = resolver.resolve(_step('role', 'APPROVER'), _ctx(ds))
    assert result.candidates == ['alice']
    assert result.source == 'user_permission_sets'


def test_unknown_role_reports_no_such_role(ds):
    result = resolver.resolve(_step('role', 'NOPE'), _ctx(ds))
    assert result.candidates == []
    assert result.reason == resolver.REASON_NO_SUCH_ROLE


def test_role_without_ref_reports_no_member(ds):
    """[M5] 缺 approver_ref：不得把 explain 当候选人返回（空池 + 原因）。"""
    result = resolver.resolve(_step('role', ''), _ctx(ds))
    assert result.candidates == []
    assert result.source == 'user_permission_sets'
    assert result.reason == resolver.REASON_NO_MEMBER
    assert result.explain[0]['field'] == 'approver_ref'


def test_group_uses_org_members(ds):
    result = resolver.resolve(_step('group', 'SALES'), _ctx(ds))
    assert result.candidates == ['bob']


def test_org_self_scope_excludes_children(ds):
    result = resolver.resolve(_step('org', 'SALES'), _ctx(ds))
    assert result.candidates == ['bob']


def test_org_descendants_scope(ds):
    result = resolver.resolve(
        _step('org', 'SALES', {'org_scope': 'descendants'}), _ctx(ds))
    assert result.candidates == ['bob', 'carol']


def test_position_matches_employee_position(ds):
    result = resolver.resolve(_step('position', 'Buyer'), _ctx(ds))
    assert result.candidates == ['bob', 'erin']


def test_job_level_exact_and_min(ds):
    assert resolver.resolve(_step('job_level', '9'), _ctx(ds)).candidates == ['carol']
    result = resolver.resolve(_step('job_level', None, {'min_job_level': 9}), _ctx(ds))
    assert result.candidates == ['carol', 'dave']


def test_manager_one_hop(ds):
    result = resolver.resolve(_step('manager'), _ctx(ds))
    assert result.candidates == ['bob']
    assert result.reason is None


def test_missing_manager_reason(ds):
    result = resolver.resolve(_step('manager'), _ctx(ds, initiator='nobody'))
    assert result.candidates == []
    assert result.reason == resolver.REASON_MISSING_MANAGER


# ───────────────────────── 汇报线 ─────────────────────────

def test_manager_chain_levels(ds):
    assert resolver.resolve(
        _step('manager_chain', None, {'levels': 2}), _ctx(ds)
    ).candidates == ['bob', 'carol']


def test_manager_chain_to_top_when_levels_zero(ds):
    result = resolver.resolve(
        _step('manager_chain', None, {'levels': 0}), _ctx(ds))
    assert result.candidates == ['bob', 'carol', 'dave']


def test_manager_chain_min_job_level_skips_low_grades(ds):
    result = resolver.resolve(
        _step('manager_chain', None, {'levels': 0, 'min_job_level': 9}), _ctx(ds))
    assert result.candidates == ['carol', 'dave']


def test_manager_chain_top_worker_sentinel(ds):
    result = resolver.resolve(
        _step('manager_chain', None, {'levels': 0, 'top_worker_id': 3}), _ctx(ds))
    assert result.candidates == ['bob', 'carol']


def test_manager_chain_include_requester(ds):
    result = resolver.resolve(
        _step('manager_chain', None, {'levels': 1, 'include': ['requester']}),
        _ctx(ds))
    assert result.candidates == ['alice', 'bob']


def test_manager_chain_has_no_n_plus_one(ds):
    """一次批量拉 employee + user：查询条数与链条长度无关。"""
    result = resolver.resolve(
        _step('manager_chain', None, {'levels': 0}), _ctx(ds))
    assert len(result.candidates) == 3
    assert len(ds.queries) <= 4, ds.queries


def test_position_hierarchy_keeps_matched_position(ds):
    result = resolver.resolve(
        _step('position_hierarchy', 'Buyer', {'levels': 0}), _ctx(ds))
    assert result.candidates == ['bob']


# ───────────────────────── 表达式 / 自选 ─────────────────────────

def test_expression_uses_rule_predicate(ds):
    result = resolver.resolve(
        _step('expression', None,
              {'expression': {'field': 'position', 'operator': 'eq',
                              'value_text': 'Buyer'}}),
        _ctx(ds))
    assert result.candidates == ['bob', 'erin']
    assert any(item['field'] == 'position' for item in result.explain)


def test_initiator_choice_reads_ctx(ds):
    ctx = dict(_ctx(ds), approver_selection=['carol'])
    result = resolver.resolve(_step('initiator_choice'), ctx)
    assert result.candidates == ['carol']


def test_unsupported_type_reports_reason(ds):
    result = resolver.resolve(_step('teleporter', 'x'), _ctx(ds))
    assert result.reason == resolver.REASON_UNSUPPORTED


# ───────────────────────── 接入建任务 ─────────────────────────

def _build_task_db():
    connection = sqlite3.connect(':memory:')
    connection.executescript(_SCHEMA + _TASK_SCHEMA)
    _seed(connection)
    connection.execute(
        'INSERT INTO purchase_orders (id, order_no, org_id, document_type_id, '
        "status, approval_status, gross_amount) VALUES (1, 'PO-1', 1, 1, "
        "'draft', 'not_required', 12000.0)")
    return connection


def test_create_task_writes_assign_explain_and_stage():
    connection = _build_task_db()
    service = ApprovalTaskService(_DS(connection))
    snapshot = {
        'policy_code': 'PO_ROLE', 'task_type': 'approval', 'amount': 12000.0,
        'steps': [{'step_no': 1, 'stage_no': 2, 'approver_type': 'role',
                   'approver_ref': 'APPROVER', 'approve_mode': 'any',
                   'action_type': 'approve', 'routing_json': None,
                   'sla_hours': None,
                   'min_amount': None, 'max_amount': None}],
    }
    task_id = service.create_task('purchase_order', 1,
                                  policy_snapshot=snapshot, actor='alice')
    assert task_id

    row = connection.execute(
        'SELECT executor_candidates, executor_config, stage_no FROM tasks '
        'WHERE id = ?', [task_id]).fetchone()
    assert json.loads(row[0]) == ['alice']
    config = json.loads(row[1])
    assert config['assign_source'] == 'user_permission_sets'
    assert config['assign_explain']
    assert 'assign_reason' not in config
    assert row[2] == 2
    connection.close()


def test_create_task_empty_pool_records_reason():
    connection = _build_task_db()
    service = ApprovalTaskService(_DS(connection))
    snapshot = {
        'policy_code': 'PO_EMPTY', 'task_type': 'approval',
        'steps': [{'step_no': 1, 'stage_no': 1, 'approver_type': 'role',
                   'approver_ref': 'NOPE', 'approve_mode': 'any',
                   'action_type': 'approve', 'routing_json': None,
                   'sla_hours': None, 'min_amount': None, 'max_amount': None}],
    }
    task_id = service.create_task('purchase_order', 1,
                                  policy_snapshot=snapshot, actor='alice')
    assert task_id
    row = connection.execute(
        'SELECT executor_candidates, executor_config FROM tasks WHERE id = ?',
        [task_id]).fetchone()
    assert json.loads(row[0]) == []
    assert json.loads(row[1])['assign_reason'] == resolver.REASON_NO_SUCH_ROLE
    connection.close()