# -*- coding: utf-8 -*-
"""ReversalOrchestrator 平台骨架（阶段 D1）：T1-T10。

用 fake schema + 记录型原语锁定编排契约（规格 §14）：
倒序 / 幂等 / 守卫 / 回滚 / 严格写面 / 投影 / 未声明 / 声明校验。
"""
import copy
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from meta.core import reversal_orchestrator as orchestrator
from meta.core.doc_effect_validator import (
    DocEffectDeclarationError,
    validate_object,
)
from meta.core.reversal_orchestrator import ReversalError, execute, supports
from meta.core.reversal_primitives import PRIMITIVES


# ─────────────────────────────────────────────────────────────────────────────
# 测试替身
# ─────────────────────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class FakeDS:
    """最小数据源：单行单据表 + 事实列表 + 嵌套事务透传 + 回滚快照。"""

    def __init__(self, **row):
        self.row = dict(row)
        self.facts = []
        self.txn_depth = 0
        self.txn_count = 0

    @property
    def in_transaction(self):
        return self.txn_depth > 0

    @contextmanager
    def transaction(self):
        if self.txn_depth:
            yield
            return
        self.txn_count += 1
        row_snapshot = copy.deepcopy(self.row)
        facts_snapshot = list(self.facts)
        self.txn_depth += 1
        try:
            yield
        except Exception:
            self.row = row_snapshot
            self.facts = facts_snapshot
            raise
        finally:
            self.txn_depth -= 1

    def query(self, sql, params=None):
        # 读：编排器只做「取单据行」一种查询
        if sql.lstrip().split(None, 1)[0].lower() == 'select':
            return [dict(self.row)]
        return []

    def execute(self, sql, params=None):
        # 写：编排器只发「按 id + status 更新单据行」一种语句
        if sql.lstrip().split(None, 1)[0].lower() == 'update':
            low = sql.lower()
            columns = [part.split('=')[0].strip()
                       for part in low.split(' set ', 1)[1]
                       .split(' where ', 1)[0].split(',')]
            for column, value in zip(columns, params or []):
                self.row[column] = value
            return _Cursor(1)
        return _Cursor(0)

    def add_fact(self, value):
        """测试替身：模拟某写面落一条事实（事务内可回滚）。"""
        self.facts.append(value)


def _schema(doc_effect, *, status_values=('shipped', 'reversed')):
    status_field = SimpleNamespace(
        id='status', db_column='status',
        enum_values=[{'value': value} for value in status_values])
    rules = [SimpleNamespace(rule_type='state_transition',
                             to_state='reversed', from_states=['shipped'])]
    return SimpleNamespace(id='fake_doc', table_name='fake_doc',
                           fields=[status_field], rules=rules,
                           doc_effect=doc_effect)


def _declaration(**overrides):
    declaration = {
        'posting': {'event_key': 'fake:{id}:{direction}',
                    'direction_field': 'category'},
        'faces': [
            {'id': 'a', 'primitive': 'fake_a'},
            {'id': 'b', 'primitive': 'fake_b',
             'args': {'event_key': '{posting.event_key}'}},
        ],
        'reversal': {
            'from_states': ['shipped'],
            'to_state': 'reversed',
            'write_audit_fields': {'reversed_at': '{now}'},
        },
    }
    declaration.update(overrides)
    return declaration


@pytest.fixture
def calls():
    saved = dict(PRIMITIVES)
    log = []
    PRIMITIVES['fake_a'] = lambda ds, args, ctx: (
        log.append(('a', args)) or {'count': 1})
    PRIMITIVES['fake_b'] = lambda ds, args, ctx: (
        log.append(('b', args)) or {'count': 1})
    yield log
    PRIMITIVES.clear()
    PRIMITIVES.update(saved)


@pytest.fixture
def bind(monkeypatch):
    def _bind(schema):
        monkeypatch.setattr(orchestrator, '_load_schema',
                            lambda schema_id: schema
                            if schema_id == schema.id else None)
    return _bind


# ─────────────────────────────────────────────────────────────────────────────
# T1 / T2 声明解析与执行序
# ─────────────────────────────────────────────────────────────────────────────

def test_t1_minimal_declaration_executes(calls, bind):
    ds = FakeDS(id=1, status='shipped', category='standard')
    bind(_schema(_declaration()))

    outcome = execute(ds, schema_id='fake_doc', doc_id=1, reason='录错')

    assert outcome.to_state == 'reversed'
    assert outcome.replay is False
    assert set(outcome.faces) == {'a', 'b'}
    assert ds.row['status'] == 'reversed'
    assert ds.row['reversed_at']
    # 默认 inverted：b 先于 a；posting 模板已解析
    assert [name for name, _ in calls] == ['b', 'a']
    assert calls[0][1] == {'event_key': 'fake:1:standard'}


def test_t2_declared_order_keeps_declaration_sequence(calls, bind):
    declaration = _declaration()
    declaration['reversal']['order'] = 'declared'
    ds = FakeDS(id=1, status='shipped', category='standard')
    bind(_schema(declaration))

    execute(ds, schema_id='fake_doc', doc_id=1)

    assert [name for name, _ in calls] == ['a', 'b']


# ─────────────────────────────────────────────────────────────────────────────
# T3 幂等重放
# ─────────────────────────────────────────────────────────────────────────────

def test_t3_idempotent_state_returns_replay_without_transaction(calls, bind):
    ds = FakeDS(id=1, status='reversed', category='standard')
    bind(_schema(_declaration()))

    outcome = execute(ds, schema_id='fake_doc', doc_id=1)

    assert outcome.replay is True
    assert calls == []
    assert ds.txn_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# T4 / T6 / T9 守卫
# ─────────────────────────────────────────────────────────────────────────────

def test_t4_state_outside_from_states_rejected(calls, bind):
    ds = FakeDS(id=1, status='draft', category='standard')
    bind(_schema(_declaration()))

    with pytest.raises(ReversalError) as error:
        execute(ds, schema_id='fake_doc', doc_id=1)
    assert error.value.code == 'REVERSAL_STATE_INVALID'
    assert calls == []


def test_t6_ref_required_when_ref_field_declared(calls, bind):
    declaration = _declaration()
    declaration['reversal']['ref_field'] = 'reversal_no'
    ds = FakeDS(id=1, status='shipped', category='standard',
                reversal_no='')
    bind(_schema(declaration))

    with pytest.raises(ReversalError) as error:
        execute(ds, schema_id='fake_doc', doc_id=1)
    assert error.value.code == 'REVERSAL_REF_MISSING'

    # 显式传入业务锚即可通过
    execute(ds, schema_id='fake_doc', doc_id=1, ref='RED-001')
    assert ds.row['status'] == 'reversed'


def test_t9_undeclared_schema_rejected(bind):
    bind(_schema({}))

    with pytest.raises(ReversalError) as error:
        execute(FakeDS(id=1, status='shipped'), schema_id='fake_doc', doc_id=1)
    assert error.value.code == 'REVERSAL_NOT_DECLARED'
    assert supports('fake_doc') is False


# ─────────────────────────────────────────────────────────────────────────────
# T5 失败全回滚
# ─────────────────────────────────────────────────────────────────────────────

def test_t5_second_face_failure_rolls_back_first(bind):
    def _write(ds, args, ctx):
        ds.add_fact(1)
        return {'count': 1}

    def _boom(ds, args, ctx):
        raise RuntimeError('boom')

    saved_a = PRIMITIVES.get('fake_a')
    PRIMITIVES['fake_a'] = _write
    PRIMITIVES['fake_b'] = _boom
    try:
        declaration = _declaration()
        declaration['reversal']['order'] = 'declared'
        ds = FakeDS(id=1, status='shipped', category='standard')
        bind(_schema(declaration))

        with pytest.raises(ReversalError) as error:
            execute(ds, schema_id='fake_doc', doc_id=1)

        assert error.value.code == 'REVERSAL_FAILED'
        assert 'fake_b' in str(error.value)
        assert ds.facts == []          # 第 1 面写入被回滚
        assert ds.row['status'] == 'shipped'
        assert ds.txn_depth == 0
    finally:
        if saved_a is not None:
            PRIMITIVES['fake_a'] = saved_a


# ─────────────────────────────────────────────────────────────────────────────
# T7 严格写面
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_strict_face_without_fact_fails(bind):
    PRIMITIVES['fake_empty'] = lambda ds, args, ctx: {'created': 0}
    saved = dict(PRIMITIVES)
    try:
        declaration = {
            'faces': [{'id': 'inventory', 'primitive': 'fake_empty',
                       'on_missing': 'strict'}],
            'reversal': {'from_states': ['shipped'], 'to_state': 'reversed'},
        }
        bind(_schema(declaration))
        with pytest.raises(ReversalError) as error:
            execute(FakeDS(id=1, status='shipped'), schema_id='fake_doc',
                    doc_id=1)
        assert error.value.code == 'REVERSAL_FACT_MISSING'
    finally:
        PRIMITIVES.clear()
        PRIMITIVES.update(saved)


def test_t7_skip_face_without_fact_passes(bind):
    PRIMITIVES['fake_empty'] = lambda ds, args, ctx: {'created': 0}
    saved = dict(PRIMITIVES)
    try:
        declaration = {
            'faces': [{'id': 'inventory', 'primitive': 'fake_empty'}],
            'reversal': {'from_states': ['shipped'], 'to_state': 'reversed'},
        }
        ds = FakeDS(id=1, status='shipped')
        bind(_schema(declaration))

        outcome = execute(ds, schema_id='fake_doc', doc_id=1)
        assert outcome.to_state == 'reversed'
        assert ds.row['status'] == 'reversed'
    finally:
        PRIMITIVES.clear()
        PRIMITIVES.update(saved)


# ─────────────────────────────────────────────────────────────────────────────
# T8 投影
# ─────────────────────────────────────────────────────────────────────────────

def test_t8_projection_runs_after_faces_with_aggregated_value(bind):
    def _write(value):
        def _primitive(ds, args, ctx):
            ds.add_fact(value)
            return {'count': 1}
        return _primitive

    def _recompute(ds, args, ctx):
        ds.row['projected'] = sum(ds.facts)
        return {'updated': 1}

    saved = dict(PRIMITIVES)
    PRIMITIVES['fake_w1'] = _write(1)
    PRIMITIVES['fake_w2'] = _write(2)
    PRIMITIVES['fake_proj'] = _recompute
    try:
        declaration = {
            'faces': [{'id': 'w1', 'primitive': 'fake_w1'},
                      {'id': 'w2', 'primitive': 'fake_w2'}],
            'projections': [{'id': 'total', 'primitive': 'fake_proj'}],
            'reversal': {'from_states': ['shipped'], 'to_state': 'reversed',
                         'order': 'declared'},
        }
        ds = FakeDS(id=1, status='shipped')
        bind(_schema(declaration))

        outcome = execute(ds, schema_id='fake_doc', doc_id=1)
        assert outcome.projections['total'] == {'updated': 1}
        assert ds.row['projected'] == 3
        assert ds.row['status'] == 'reversed'
    finally:
        PRIMITIVES.clear()
        PRIMITIVES.update(saved)


# ─────────────────────────────────────────────────────────────────────────────
# T10 声明校验（V1-V6）
# ─────────────────────────────────────────────────────────────────────────────

def test_t10_from_states_mismatch_rejected(calls, bind):
    declaration = _declaration()
    declaration['reversal']['from_states'] = ['posted']
    schema = _schema(declaration)
    bind(schema)

    with pytest.raises(DocEffectDeclarationError) as error:
        validate_object(schema)
    assert error.value.code == 'DECL_STATE_MISMATCH'

    with pytest.raises(ReversalError) as orchestrator_error:
        execute(FakeDS(id=1, status='shipped'), schema_id='fake_doc', doc_id=1)
    assert orchestrator_error.value.code == 'REVERSAL_DECL_INVALID'
    assert calls == []


def test_declaration_unknown_primitive_rejected():
    declaration = _declaration()
    declaration['faces'][0]['primitive'] = 'no_such_primitive'
    with pytest.raises(DocEffectDeclarationError) as error:
        validate_object(_schema(declaration))
    assert error.value.code == 'DECL_UNKNOWN_PRIMITIVE'


def test_declaration_duplicate_face_rejected():
    declaration = _declaration()
    declaration['faces'][1]['id'] = declaration['faces'][0]['id']
    with pytest.raises(DocEffectDeclarationError) as error:
        validate_object(_schema(declaration))
    assert error.value.code == 'DECL_DUPLICATE_FACE'


def test_declaration_compensation_requires_ref_field():
    declaration = {
        'faces': [{'id': 'doc_flow', 'primitive': 'edge_compensate_by_source',
                   'args': {'source_bo': 'fake_line',
                            'rule_ids': ['fake_rule']}}],
        'reversal': {'from_states': ['shipped'], 'to_state': 'reversed'},
    }
    with pytest.raises(DocEffectDeclarationError) as error:
        validate_object(_schema(declaration))
    assert error.value.code == 'DECL_REF_FIELD_REQUIRED'


def test_declaration_unresolved_placeholder_rejected():
    declaration = _declaration()
    declaration['faces'][0]['args'] = {'event_key': '{no_such_root.key}'}
    with pytest.raises(DocEffectDeclarationError) as error:
        validate_object(_schema(declaration))
    assert error.value.code == 'DECL_UNRESOLVED_PLACEHOLDER'
