# -*- coding: utf-8 -*-
"""派生度量注册表测试（M3 / FR-003 / NFR-003）

覆盖三块：
  ① 定义与注册期校验（结构 / 重复 / 未声明输入 / 循环依赖）
  ② MetricSession 单次计算 + 精度 + derived_cache 标记
  ③ 审批解析引用度量（条件 field_id = 度量 code），且派生值不写回单据
"""

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

pytestmark = pytest.mark.unit

from meta.core.rule_declaration_validator import validate_metric_definitions
from meta.core.rule_metrics import (
    MetricDefinition,
    MetricError,
    MetricRegistry,
    MetricSession,
)
from meta.services.document_approval_service import DocumentApprovalResolver


# ---------------- ① 定义与注册 ----------------

def test_definition_normalizes_inputs():
    definition = MetricDefinition(
        code=' diff ', formula=' net_amount - tax_amount ',
        inputs=['net_amount', ' tax_amount ', 'net_amount'], precision=2)
    assert definition.code == 'diff'
    assert definition.formula == 'net_amount - tax_amount'
    assert definition.inputs == ('net_amount', 'tax_amount')


@pytest.mark.parametrize('kwargs', [
    {'code': '', 'formula': 'a + b'},
    {'code': 'x', 'formula': '   '},
    {'code': 'x', 'formula': 'a', 'precision': -1},
    {'code': 'x', 'formula': 'a', 'precision': 13},
    {'code': 'x', 'formula': 'a', 'precision': '2'},
    {'code': 'x', 'formula': 'a', 'inputs': ['']},
])
def test_definition_rejects_structural_errors(kwargs):
    with pytest.raises(MetricError):
        MetricDefinition(**kwargs)


def test_registry_rejects_duplicate():
    registry = MetricRegistry()
    registry.register(MetricDefinition('amount', 'a + b', inputs=['a', 'b']))
    with pytest.raises(MetricError):
        registry.register(MetricDefinition('amount', 'a - b', inputs=['a', 'b']))


def test_registry_global_scope_fallback():
    registry = MetricRegistry()
    registry.register(MetricDefinition('rate', '0.13'))
    assert registry.get('purchase_order', 'rate') is not None
    assert registry.codes('purchase_order') == ['rate']


def test_validate_reports_undeclared_input():
    registry = MetricRegistry()
    registry.register(MetricDefinition('amount', 'a + b', inputs=['a']))
    errors = registry.validate()
    assert any('未声明的输入 b' in message for message in errors)


def test_validate_reports_unknown_input_with_known_fields():
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'amount', 'gross_amount * 2', inputs=['gross_amount'],
        object_type='purchase_order'))
    errors = registry.validate(known_fields={'purchase_order': {'net_amount'}})
    assert any('既不是度量也不是该对象字段' in message for message in errors)
    assert registry.validate(
        known_fields={'purchase_order': {'gross_amount'}}) == []


def test_validate_reports_cycle():
    registry = MetricRegistry()
    registry.register(MetricDefinition('a', 'b + 1', inputs=['b']))
    registry.register(MetricDefinition('b', 'a + 1', inputs=['a']))
    errors = registry.validate()
    assert any('度量循环依赖' in message for message in errors)


def test_declaration_validator_wraps_metric_errors():
    registry = MetricRegistry()
    registry.register(MetricDefinition('a', 'b + 1', inputs=['b']))
    registry.register(MetricDefinition('b', 'a + 1', inputs=['a']))
    errors = validate_metric_definitions(registry)
    assert errors
    assert all(e.code == 'METRIC_DEFINITION_INVALID' for e in errors)


# ---------------- ② MetricSession ----------------

def test_session_computes_metric_once_for_multiple_references():
    calls = []

    def evaluator(formula, bindings):
        calls.append((formula, dict(bindings)))
        return eval(formula, {}, bindings)  # noqa: S307 - 测试内固定公式

    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'double_amount', 'gross_amount * 2', inputs=['gross_amount']))
    registry.register(MetricDefinition(
        'triple_double', 'double_amount * 3', inputs=['double_amount']))

    session = MetricSession(
        'purchase_order', 1, {'gross_amount': 100}, registry, evaluator)
    assert session.resolve('triple_double') == 600
    assert session.resolve('triple_double') == 600
    assert session.resolve('double_amount') == 200

    formulas = [formula for formula, _ in calls]
    assert formulas.count('gross_amount * 2') == 1
    assert formulas.count('double_amount * 3') == 1
    assert session.computed_codes == ['double_amount', 'triple_double']


def test_session_snapshot_marks_derived_cache():
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'double_amount', 'gross_amount * 2', inputs=['gross_amount'],
        unit='CNY', precision=2))
    session = MetricSession('purchase_order', 1, {'gross_amount': 10.005},
                            registry, lambda f, b: b['gross_amount'] * 2)
    session.resolve('double_amount')
    entry = session.snapshot()['double_amount']
    assert entry['derived_cache'] is True
    assert entry['unit'] == 'CNY'
    assert entry['precision'] == 2
    assert entry['value'] == 20.01


def test_session_precision_rounding_with_default_evaluator():
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'third', 'net_amount / 3', inputs=['net_amount'], precision=2))
    session = MetricSession('purchase_order', 1, {'net_amount': 10}, registry)
    assert session.resolve('third') == 3.33


def test_session_enrich_does_not_mutate_record():
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'double_amount', 'gross_amount * 2', inputs=['gross_amount']))
    record = {'gross_amount': 50}
    session = MetricSession('purchase_order', 1, record, registry)
    merged = session.enrich(record, ['double_amount', 'unknown_metric'])
    assert merged == {'gross_amount': 50, 'double_amount': 100}
    assert record == {'gross_amount': 50}


def test_session_unknown_metric_raises():
    with pytest.raises(MetricError):
        MetricSession('purchase_order', 1, {}, MetricRegistry()).resolve('nope')


# ---------------- ③ 审批解析引用度量 ----------------

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
"""


class _MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:')
    connection.executescript(_SCHEMA)
    yield connection
    connection.close()


def _seed_metric_approval(connection):
    connection.execute(
        'INSERT INTO purchase_orders (id, order_no, org_id, document_type_id, '
        'status, approval_status, gross_amount, net_amount) '
        "VALUES (1, 'PO-1', 1, 1, 'draft', 'not_required', 12000.0, 10000.0)")
    connection.execute(
        'INSERT INTO approval_policies (id, code, name, scope_bo, trigger_action, '
        "status, priority) VALUES (1, 'PO_METRIC', 'PO', 'purchase_order', "
        "'submit', 'active', 0)")
    connection.execute(
        'INSERT INTO approval_policy_conditions (id, policy_id, group_no, field_id, '
        "operator, value_number) VALUES (1, 1, 1, 'amount_doubled', '>=', 20000)")
    connection.execute(
        'INSERT INTO approval_policy_steps (id, policy_id, step_no, approver_type, '
        "approver_ref, approve_mode, sla_hours) VALUES (1, 1, 1, 'role', "
        "'manager', 'any', 24)")


def test_approval_condition_can_reference_metric(conn):
    _seed_metric_approval(conn)
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'amount_doubled', 'gross_amount * 2', inputs=['gross_amount'],
        object_type='purchase_order', unit='CNY', precision=2))

    result = DocumentApprovalResolver(_MemDS(conn), registry).resolve(
        'purchase_order', 1)
    assert result['required'] is True
    assert result['policy_code'] == 'PO_METRIC'

    metrics = result['snapshot']['metrics']
    assert set(metrics) == {'amount_doubled'}
    assert metrics['amount_doubled']['value'] == 24000.0
    assert metrics['amount_doubled']['derived_cache'] is True
    explain = result['snapshot']['conditions_explain']
    assert explain == [{'field': 'amount_doubled', 'op': 'ge', 'expected': 20000,
                        'actual': 24000.0, 'passed': True}]


def test_approval_metric_miss_and_not_persisted(conn):
    _seed_metric_approval(conn)
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'amount_doubled', 'gross_amount * 2', inputs=['gross_amount'],
        object_type='purchase_order', precision=2))

    # 降低单头金额 → 度量不达阈值 → 免审批
    conn.execute('UPDATE purchase_orders SET gross_amount = 100')
    result = DocumentApprovalResolver(_MemDS(conn), registry).resolve(
        'purchase_order', 1)
    assert result['required'] is False
    assert result['reason'] == 'no_policy'

    # 派生值只在会话内，不写回单据行
    row = _MemDS(conn).query('SELECT * FROM purchase_orders WHERE id = 1')[0]
    assert 'amount_doubled' not in row
    assert row['gross_amount'] == 100


# ---------------- ④ YAML metrics: 声明 → 注册表（M6a-3） ----------------

def _schema_path(name: str) -> str:
    from meta.core.yaml_loader import get_yaml_schema_dir
    return str(Path(get_yaml_schema_dir()) / name)


def test_yaml_metrics_section_parsed_to_metric_definitions():
    from meta.core.yaml_loader import load_yaml_file

    obj = load_yaml_file(_schema_path('inventory_count_line.yaml'))
    assert obj is not None
    assert [d.code for d in obj.metrics] == ['deviation_qty', 'deviation_rate']
    assert obj.metrics[0].object_type == 'inventory_count_line'
    assert obj.metrics[0].inputs == ('counted_qty', 'snapshot_qty')
    assert obj.metrics[1].inputs == ('deviation_qty', 'snapshot_qty')
    # L0 派生度量与 analytical_model（报表语义层）严格分离
    assert not obj.analytical_model


def test_yaml_metrics_reject_invalid_declarations():
    from meta.core.yaml_loader import _parse_metric_definitions

    with pytest.raises(ValueError):
        _parse_metric_definitions('demo', {'code': 'x', 'formula': 'a'})
    with pytest.raises(ValueError):
        _parse_metric_definitions('demo', [
            {'code': 'x', 'formula': 'a', 'inputs': ['a']},
            {'code': 'x', 'formula': 'b', 'inputs': ['b']},
        ])
    with pytest.raises(MetricError):
        _parse_metric_definitions('demo', [{'code': 'x'}])


def test_register_metric_definitions_is_idempotent():
    from meta.core.rule_metrics import DEFAULT_METRIC_REGISTRY
    from meta.core.yaml_loader import register_metric_definitions

    scope = '_m6a3_demo'
    obj = SimpleNamespace(metrics=[
        MetricDefinition('deviation_qty', 'counted_qty - snapshot_qty',
                         inputs=['counted_qty', 'snapshot_qty'],
                         object_type=scope),
        MetricDefinition('deviation_rate', 'deviation_qty / snapshot_qty',
                         inputs=['deviation_qty', 'snapshot_qty'],
                         precision=4, object_type=scope),
    ])
    try:
        assert register_metric_definitions([obj]) == 2
        # 目录重复加载 / reload 幂等：覆盖而不是抛「重复定义」
        assert register_metric_definitions([obj]) == 2
        assert DEFAULT_METRIC_REGISTRY.codes(scope) == [
            'deviation_qty', 'deviation_rate']
        errors = validate_metric_definitions(
            known_fields={scope: {'counted_qty', 'snapshot_qty'}})
        assert not [e for e in errors if e.message.startswith(scope + '.')]
    finally:
        DEFAULT_METRIC_REGISTRY.replace_scope(scope, [])


def test_register_from_directory_feeds_default_registry():
    from meta.core.rule_metrics import DEFAULT_METRIC_REGISTRY
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    register_from_directory(get_yaml_schema_dir(), target={})
    codes = DEFAULT_METRIC_REGISTRY.codes('inventory_count_line')
    assert 'deviation_qty' in codes
    assert 'deviation_rate' in codes


def test_metric_session_resolves_deviation_metrics_once():
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        'deviation_qty', 'counted_qty - snapshot_qty',
        inputs=['counted_qty', 'snapshot_qty'],
        object_type='inventory_count_line'))
    registry.register(MetricDefinition(
        'deviation_rate', 'deviation_qty / snapshot_qty',
        inputs=['deviation_qty', 'snapshot_qty'],
        object_type='inventory_count_line', precision=4))

    session = MetricSession(
        'inventory_count_line', 1,
        {'counted_qty': 12, 'snapshot_qty': 10}, registry)
    assert session.resolve('deviation_qty') == 2.0
    assert session.resolve('deviation_rate') == 0.2

    snapshot = session.snapshot()
    assert set(snapshot) == {'deviation_qty', 'deviation_rate'}
    assert all(item['derived_cache'] is True for item in snapshot.values())