# -*- coding: utf-8 -*-
"""P5 批次选择策略与选择算法测试（spec §12.5–§12.6 / §7.2）。

覆盖:
  · YAML / 表结构 / 3 索引（含部分唯一条件）/ 3 值枚举 / priority >= 1。
  · BatchSelectionPolicyService：范围存在性、active priority 唯一、rule_json v1
    白名单（JSON / 未知键 / EAV / 未知算子 / limit / version）、3 个模板、rule_hash。
  · BatchSelectionService：item → item_group → org、同层 priority、首条命中、
    0 条下探、无策略 / 全 0、默认可用性谓词、allow_blocked、grade NULL 最后、
    qty/uom 透传、成功与失败审计载荷。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
import pathlib
import sqlite3
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from meta.services.batch_selection_policy_service import (  # noqa: E402
    BatchSelectionPolicyError,
    BatchSelectionPolicyService,
    RULE_TEMPLATES,
)
from meta.services.batch_selection_service import (  # noqa: E402
    BatchSelectionService,
    NoBatchMatchError,
)

pytestmark = pytest.mark.unit

SCHEMA_DIR = ROOT / 'meta' / 'schemas'

BASE_SCHEMA = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT,
    base_uom INTEGER, item_group_id INTEGER
);
CREATE TABLE orgs (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE uoms (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT,
                   uom_group_id INTEGER);
CREATE TABLE item_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT);
CREATE TABLE attribute_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER DEFAULT 0,
    code TEXT, name TEXT, data_type TEXT DEFAULT 'string',
    multi_value_flag INTEGER DEFAULT 0, status TEXT DEFAULT 'active'
);
"""


def _load_yaml(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _index(doc, name):
    return next(i for i in doc['indexes'] if i.get('name') == name)


class MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


class FakeAudit:
    def __init__(self):
        self.calls = []

    def log(self, **kwargs):
        self.calls.append(kwargs)


def _policy_table_ddl(conn):
    from meta.migrations import v199__routing_p5 as v199
    for _name, ddl in v199.TABLES:
        conn.execute(ddl)
    for table, name, sql in v199.INDEXES:
        if table == 'batch_selection_policies':
            conn.execute(sql)


def _build_db(seed_batches=False):
    conn = sqlite3.connect(':memory:')
    conn.executescript(BASE_SCHEMA)
    _policy_table_ddl(conn)
    if seed_batches:
        from meta.migrations import v196__batch_foundation as v196
        from meta.migrations import v199__routing_p5 as v199
        for _name, ddl in v196.TABLES:
            conn.execute(ddl)
        # P5：batches.grade_code 由 v199 追加列
        for table, column, ddl in v199.ADDED_COLUMNS:
            if table == 'batches':
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')
    conn.executemany(
        'INSERT INTO items (id, code, base_uom, item_group_id) '
        'VALUES (?, ?, ?, ?)',
        [(1, 'ITEM1', 1, 1), (2, 'ITEM2', 1, None)])
    conn.execute("INSERT INTO orgs (id, code) VALUES (1, 'PLANT1')")
    conn.execute("INSERT INTO item_groups (id, code) VALUES (1, 'FG')")
    conn.execute("INSERT INTO attribute_definitions (id, code, name) "
                 "VALUES (1, 'color', '颜色')")
    return conn


def _policy_payload(**kwargs):
    data = {
        'code': 'P1',
        'name': '策略1',
        'scope_type': 'item',
        'scope_ref': 'ITEM1',
        'priority': 1,
        'status': 'active',
        'rule_json': {'version': 1},
    }
    data.update(kwargs)
    return data


def _expect_policy(service, payload, rule, existing=None):
    with pytest.raises(BatchSelectionPolicyError) as exc:
        service.validate_policy(payload, existing)
    assert exc.value.rule == rule
    return exc.value


def _add_policy(conn, code, scope_type, scope_ref, rule, priority=1,
                status='active'):
    cur = conn.execute(
        'INSERT INTO batch_selection_policies '
        '(code, name, scope_type, scope_ref, rule_json, priority, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        [code, code, scope_type, scope_ref, json.dumps(rule), priority, status])
    return cur.lastrowid


def _add_batch(conn, batch_id, batch_no, item_id=1, org_id=1, grade=None,
               status='planned', quality='unrestricted', qty=10,
               expiry='2027-01-01'):
    conn.execute(
        'INSERT INTO batches (id, batch_no, item_id, org_id, qty, qty_uom_id, '
        'status, quality_status, source, grade_code, expiry_date) '
        'VALUES (?, ?, ?, ?, ?, 1, ?, ?, \'manual\', ?, ?)',
        [batch_id, batch_no, item_id, org_id, qty, status, quality, grade, expiry])


# ---------------------------------------------------------------------------
# YAML / 表结构
# ---------------------------------------------------------------------------
def test_policy_yaml_declared():
    doc = _load_yaml('batch_selection_policy.yaml')
    assert doc['id'] == 'batch_selection_policy'
    assert doc['table_name'] == 'batch_selection_policies'
    ids = {f['id'] for f in doc['fields']}
    assert {'code', 'name', 'scope_type', 'scope_ref', 'rule_json',
            'priority', 'status', 'description'} <= ids

    scope = next(f for f in doc['fields'] if f['id'] == 'scope_type')
    assert {v['value'] for v in scope['enum_values']} == {
        'item', 'item_group', 'org'}
    status = next(f for f in doc['fields'] if f['id'] == 'status')
    assert {v['value'] for v in status['enum_values']} == {'active', 'inactive'}
    priority = next(f for f in doc['fields'] if f['id'] == 'priority')
    assert priority['constraints'][0]['gte'] == 1

    partial = _index(doc, 'uq_batch_selection_policy_scope_priority')
    assert partial['type'] == 'partial'
    assert partial['condition'] == "status = 'active'"
    assert _index(doc, 'uq_batch_selection_policy_code')['unique'] is True
    assert _index(doc, 'idx_batch_selection_policy_scope')['fields'] == [
        'scope_type', 'scope_ref']

    assert doc['ui_view_config']['skip_auto_menu'] is False
    assert {'list', 'form', 'detail'} <= set(doc['ui_view_config'])


def test_policy_table_and_indexes_real():
    conn = _build_db()
    info = {row[1]: row for row in conn.execute(
        'PRAGMA table_info(batch_selection_policies)')}
    for col in ('code', 'name', 'scope_type', 'scope_ref', 'rule_json',
                'priority', 'status', 'description'):
        assert col in info
    assert info['priority'][3] == 1
    assert str(info['priority'][4]) == '1'

    for name in ('uq_batch_selection_policy_code',
                 'uq_batch_selection_policy_scope_priority',
                 'idx_batch_selection_policy_scope'):
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone() is not None
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        ('uq_batch_selection_policy_scope_priority',)).fetchone()[0]
    assert "WHERE status = 'active'" in sql

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            'INSERT INTO batch_selection_policies '
            '(code, name, scope_type, scope_ref, rule_json, priority) '
            "VALUES ('BAD', 'BAD', 'item', 'ITEM1', '{\"version\":1}', 0)")


# ---------------------------------------------------------------------------
# 策略保存校验
# ---------------------------------------------------------------------------
def test_policy_valid_and_canonical():
    conn = _build_db()
    service = BatchSelectionPolicyService(MemDS(conn))
    merged = service.validate_policy(_policy_payload())
    rule = json.loads(merged['rule_json'])
    assert rule == {
        'version': 1, 'filters': [], 'sort': [], 'limit': 100,
        'allow_blocked': False}
    assert merged['status'] == 'active'
    assert merged['priority'] == 1


def test_policy_scope_must_exist():
    conn = _build_db()
    service = BatchSelectionPolicyService(MemDS(conn))
    _expect_policy(service, _policy_payload(scope_ref='NOPE'),
                   'BATCH_SELECTION_SCOPE_NOT_FOUND')
    _expect_policy(service, _policy_payload(scope_type='bad'),
                   'BATCH_SELECTION_SCOPE_INVALID')


def test_policy_active_priority_unique():
    conn = _build_db()
    service = BatchSelectionPolicyService(MemDS(conn))
    _add_policy(conn, 'EXIST', 'item', 'ITEM1', {'version': 1}, priority=1)
    _expect_policy(service, _policy_payload(code='P2'),
                   'BATCH_SELECTION_PRIORITY_DUPLICATE')
    merged = service.validate_policy(_policy_payload(
        code='P3', status='inactive'))
    assert merged['status'] == 'inactive'


def test_policy_rule_whitelist():
    conn = _build_db()
    service = BatchSelectionPolicyService(MemDS(conn))
    _expect_policy(service, _policy_payload(rule_json='{bad json'),
                   'BATCH_SELECTION_RULE_INVALID_JSON')
    _expect_policy(service, _policy_payload(
        rule_json={'version': 1, 'unknown': 1}),
        'BATCH_SELECTION_RULE_UNKNOWN_KEY')
    _expect_policy(service, _policy_payload(rule_json={'version': 2}),
                   'BATCH_SELECTION_RULE_VERSION')
    _expect_policy(service, _policy_payload(
        rule_json={'version': 1, 'filters': [
            {'field': 'foo', 'op': 'eq', 'value': 'x'}]}),
        'BATCH_SELECTION_RULE_UNKNOWN_FIELD')
    _expect_policy(service, _policy_payload(
        rule_json={'version': 1, 'filters': [
            {'field': 'color', 'op': 'eq', 'value': 'red'}]}),
        'BATCH_SELECTION_EAV_FIELD_NOT_ALLOWED')
    _expect_policy(service, _policy_payload(
        rule_json={'version': 1, 'filters': [
            {'field': 'batch_no', 'op': 'xx', 'value': 'B1'}]}),
        'BATCH_SELECTION_RULE_UNKNOWN_OP')
    _expect_policy(service, _policy_payload(
        rule_json={'version': 1, 'limit': 0}),
        'BATCH_SELECTION_RULE_VALUE_INVALID')
    _expect_policy(service, _policy_payload(
        rule_json={'version': 1, 'filters': [
            {'field': 'qty', 'op': 'gt', 'value': 'x'}]}),
        'BATCH_SELECTION_RULE_VALUE_INVALID')


def test_rule_templates_and_hash():
    service = BatchSelectionPolicyService(None)
    for template in RULE_TEMPLATES.values():
        normalized = service.validate_rule_json(template)
        assert normalized['limit'] == 100

    one = BatchSelectionPolicyService.rule_hash({'version': 1})
    two = BatchSelectionPolicyService.rule_hash('{"version":1}')
    assert one == two
    assert len(one) == 16


# ---------------------------------------------------------------------------
# 选择算法
# ---------------------------------------------------------------------------
def _selection(conn, audit=None):
    return BatchSelectionService(MemDS(conn), audit_service=audit)


def test_scope_order_item_over_group_and_org():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-A', grade='A')
    _add_batch(conn, 2, 'B-B', grade='B')
    _add_policy(conn, 'ITEM', 'item', 'ITEM1',
                {'version': 1, 'filters': [
                    {'field': 'grade_code', 'op': 'eq', 'value': 'A'}]},
                priority=2)
    _add_policy(conn, 'GROUP', 'item_group', 'FG',
                {'version': 1, 'filters': [
                    {'field': 'grade_code', 'op': 'eq', 'value': 'B'}]},
                priority=1)
    _add_policy(conn, 'ORG', 'org', 'PLANT1', {'version': 1}, priority=1)

    result = _selection(conn).select_batches(1, 1)
    assert result.batch_ids == [1]
    assert result.policy_id == 1
    assert result.evaluated_policies == ['ITEM']


def test_same_scope_priority_and_zero_result_falls_through():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-A', grade='A')
    _add_batch(conn, 2, 'B-B', grade='B')
    _add_policy(conn, 'LOW', 'item', 'ITEM1',
                {'version': 1, 'filters': [
                    {'field': 'grade_code', 'op': 'eq', 'value': 'Z'}]},
                priority=1)
    _add_policy(conn, 'HIGH', 'item', 'ITEM1',
                {'version': 1, 'filters': [
                    {'field': 'grade_code', 'op': 'eq', 'value': 'A'}]},
                priority=2)

    result = _selection(conn).select_batches(1, 1)
    assert result.batch_ids == [1]
    assert result.evaluated_policies == ['LOW', 'HIGH']


def test_first_hit_stops_evaluation():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-A', grade='A')
    _add_batch(conn, 2, 'B-B', grade='B')
    _add_policy(conn, 'FIRST', 'item', 'ITEM1',
                {'version': 1, 'filters': [
                    {'field': 'grade_code', 'op': 'eq', 'value': 'A'}]},
                priority=1)
    _add_policy(conn, 'SECOND', 'item', 'ITEM1',
                {'version': 1, 'filters': [
                    {'field': 'grade_code', 'op': 'eq', 'value': 'B'}]},
                priority=2)

    result = _selection(conn).select_batches(1, 1)
    assert result.batch_ids == [1]
    assert result.evaluated_policies == ['FIRST']


def test_no_policy_raises_and_audits_failure():
    conn = _build_db(seed_batches=True)
    audit = FakeAudit()
    with pytest.raises(NoBatchMatchError) as exc:
        _selection(conn, audit).select_batches(2, 9)
    assert exc.value.reason == 'no_policy'
    assert exc.value.attempted_policy_codes == []
    assert audit.calls[-1]['outcome'] == 'failed'
    assert audit.calls[-1]['extra_data']['reason'] == 'no_policy'


def test_all_policies_zero_raises_no_match():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-A', grade='A')
    _add_policy(conn, 'P-Z', 'item', 'ITEM1',
                {'version': 1, 'filters': [
                    {'field': 'grade_code', 'op': 'eq', 'value': 'Z'}]})
    audit = FakeAudit()
    with pytest.raises(NoBatchMatchError) as exc:
        _selection(conn, audit).select_batches(1, 1)
    assert exc.value.reason == 'no_match'
    assert exc.value.attempted_policy_codes == ['P-Z']
    assert audit.calls[-1]['extra_data']['reason'] == 'no_match'


def test_default_predicate_excludes_blocked_inspection_closed():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-BLOCK', status='planned', quality='blocked')
    _add_batch(conn, 2, 'B-INSPEC', status='planned', quality='inspection')
    _add_batch(conn, 3, 'B-CLOSED', status='closed', quality='unrestricted')
    _add_batch(conn, 4, 'B-OK', status='planned', quality='unrestricted')
    _add_policy(conn, 'DEFAULT', 'item', 'ITEM1',
                {'version': 1, 'limit': 10})

    result = _selection(conn).select_batches(1, 1)
    assert result.batch_ids == [4]
    assert result.default_predicate == (
        "quality_status = 'unrestricted' AND status != 'closed'")
    assert result.allow_blocked is False


def test_allow_blocked_opens_blocked_and_inspection_but_not_closed():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-BLOCK', status='planned', quality='blocked')
    _add_batch(conn, 2, 'B-INSPEC', status='planned', quality='inspection')
    _add_batch(conn, 3, 'B-CLOSED', status='closed', quality='unrestricted')
    _add_batch(conn, 4, 'B-OK', status='planned', quality='unrestricted')
    _add_policy(conn, 'OPEN', 'item', 'ITEM1',
                {'version': 1, 'limit': 10, 'allow_blocked': True})

    result = _selection(conn).select_batches(1, 1)
    assert result.batch_ids == [1, 2, 4]
    assert result.default_predicate == "status != 'closed'"
    assert result.allow_blocked is True


def test_grade_sort_puts_nulls_last():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-A', grade='A')
    _add_batch(conn, 2, 'B-C', grade='C')
    _add_batch(conn, 3, 'B-NONE', grade=None)
    _add_policy(conn, 'ASC', 'item', 'ITEM1', {
        'version': 1,
        'sort': [{'field': 'grade_code', 'dir': 'asc'}],
    })
    assert _selection(conn).select_batches(1, 1).batch_ids == [1, 2, 3]

    conn.execute('DELETE FROM batch_selection_policies')
    _add_policy(conn, 'DESC', 'item', 'ITEM1', {
        'version': 1,
        'sort': [{'field': 'grade_code', 'dir': 'desc'}],
    })
    assert _selection(conn).select_batches(1, 1).batch_ids == [2, 1, 3]


def test_qty_uom_pass_through_does_not_filter():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-A', grade='A')
    _add_policy(conn, 'P', 'item', 'ITEM1', {'version': 1})
    audit = FakeAudit()
    service = _selection(conn, audit)

    low = service.select_batches(1, 1, qty=1, uom='KG')
    high = service.select_batches(1, 1, qty=500, uom='KG')
    assert low.batch_ids == high.batch_ids == [1]
    assert audit.calls[-1]['extra_data']['qty'] == 500
    assert audit.calls[-1]['extra_data']['uom'] == 'KG'


def test_success_audit_payload():
    conn = _build_db(seed_batches=True)
    _add_batch(conn, 1, 'B-A', grade='A')
    _add_policy(conn, 'P', 'item', 'ITEM1', {'version': 1})
    audit = FakeAudit()
    result = _selection(conn, audit).select_batches(1, 1, qty=10, uom='KG')

    call = audit.calls[-1]
    extra = call['extra_data']
    assert call['object_type'] == 'batch_selection_policy'
    assert call['object_id'] == 1
    assert call['action'] == 'select'
    assert call['outcome'] == 'success'
    assert extra['item_code'] == 'ITEM1'
    assert extra['org_code'] == 'PLANT1'
    assert extra['batch_ids'] == [1]
    assert extra['policy_code'] == 'P'
    assert extra['priority'] == 1
    assert len(extra['rule_hash']) == 16
    assert extra['default_predicate'] == (
        "quality_status = 'unrestricted' AND status != 'closed'")
    assert extra['allow_blocked'] is False
    assert extra['attempted_policy_codes'] == ['P']
    assert result.rule_hash == extra['rule_hash']
