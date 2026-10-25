# -*- coding: utf-8 -*-
"""控制参数解析测试（命中链 / 具体度 / 值类型解释 / 停用过滤）

依据: meta/schemas/control_parameter_def.yaml 与 control_parameter_value.yaml 头注释
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services.control_parameter_service import (
    ControlParameterResolver,
    get_control_parameter_resolver,
)


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源：按 YAML 里的两条装载 SQL 的语义过滤 active
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, defs=None, values=None, raise_on_query=False):
        self.defs = defs or []
        self.values = values or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        if 'FROM control_parameter_defs' in sql:
            return [d for d in self.defs if d.get('status') == 'active']
        if 'FROM control_parameter_values' in sql:
            return [v for v in self.values if v.get('status') == 'active']
        raise AssertionError(f'未预期的 SQL: {sql}')


def _def(code='allow_partial_delivery', value_type='bool', default='true', **kw):
    row = {'id': kw.pop('id', 1), 'code': code, 'domain': kw.pop('domain', 'sales'),
           'value_type': value_type, 'default_value': default,
           'enum_type_id': kw.pop('enum_type_id', None),
           'target_bo': kw.pop('target_bo', None),
           'status': kw.pop('status', 'active')}
    row.update(kw)
    return row


def _val(param_id=1, value='false', rank=None, **kw):
    row = {'id': kw.pop('id', 1), 'control_parameter_id': param_id, 'value': value,
           'specificity_rank': rank, 'org_id': kw.pop('org_id', None),
           'document_type_id': kw.pop('document_type_id', None),
           'line_type_id': kw.pop('line_type_id', None),
           'item_group_id': kw.pop('item_group_id', None),
           'status': kw.pop('status', 'active')}
    row.update(kw)
    return row


def _resolver(defs=None, values=None, **kw):
    return ControlParameterResolver(_FakeDS(defs=defs, values=values, **kw))


# ─────────────────────────────────────────────────────────────────────────────
# 命中链
# ─────────────────────────────────────────────────────────────────────────────

class TestResolve:
    def test_falls_back_to_default_when_no_row_matches(self):
        r = _resolver(defs=[_def(default='true')], values=[])
        assert r.resolve('allow_partial_delivery', {'org_id': 1}) is True

    def test_wildcard_row_wins_over_default(self):
        r = _resolver(defs=[_def(default='true')],
                      values=[_val(value='false', rank=900)])
        assert r.resolve('allow_partial_delivery', {'org_id': 1}) is False

    def test_more_specific_rank_wins(self):
        r = _resolver(
            defs=[_def(default='true')],
            values=[_val(id=1, value='false', rank=900),
                    _val(id=2, value='true', rank=100, org_id=1)],
        )
        assert r.resolve('allow_partial_delivery', {'org_id': 1}) is True
        assert r.resolve('allow_partial_delivery', {'org_id': 2}) is False

    def test_row_requiring_missing_dimension_does_not_match(self):
        r = _resolver(defs=[_def(default='true')],
                      values=[_val(value='false', rank=100, org_id=1)])
        # 调用方没给 org_id ⇒ 含该维度的行不命中
        assert r.resolve('allow_partial_delivery', {}) is True

    def test_dimension_mismatch_does_not_match(self):
        r = _resolver(defs=[_def(default='true')],
                      values=[_val(value='false', rank=100, item_group_id=7)])
        assert r.resolve('allow_partial_delivery', {'item_group_id': 8}) is True

    def test_inactive_value_is_ignored(self):
        r = _resolver(defs=[_def(default='true')],
                      values=[_val(value='false', rank=10, status='inactive')])
        assert r.resolve('allow_partial_delivery', {}) is True

    def test_inactive_def_returns_none(self):
        r = _resolver(defs=[_def(default='true', status='inactive')])
        assert r.resolve('allow_partial_delivery', {}) is None

    def test_unknown_code_returns_none(self):
        r = _resolver(defs=[_def()])
        assert r.resolve('not_exists', {}) is None

    def test_resolve_many_shares_one_load(self):
        r = _resolver(defs=[_def(id=1, default='true'),
                            _def(id=2, code='default_payment_term',
                                 value_type='ref', default='3',
                                 target_bo='payment_term')],
                      values=[_val(param_id=1, value='false', rank=10)])
        got = r.resolve_many(['allow_partial_delivery', 'default_payment_term', 'x'],
                             {'org_id': 1})
        assert got == {'allow_partial_delivery': False,
                       'default_payment_term': 3, 'x': None}

    def test_domain_filter_excludes_other_domain(self):
        r = _resolver(defs=[_def(default='true', domain='procurement')])
        assert r.resolve_many(['allow_partial_delivery'], {}, domain='sales') == {
            'allow_partial_delivery': None}
        assert r.resolve_many(['allow_partial_delivery'], {}, domain='procurement') == {
            'allow_partial_delivery': True}

    def test_load_failure_returns_none_without_raising(self):
        r = _resolver(raise_on_query=True)
        assert r.resolve('allow_partial_delivery', {}) is None


# ─────────────────────────────────────────────────────────────────────────────
# 值类型解释
# ─────────────────────────────────────────────────────────────────────────────

class TestConvert:
    @pytest.mark.parametrize('raw,expected', [
        ('true', True), ('TRUE', True), ('1', True),
        ('false', False), ('0', False), ('否', False),
    ])
    def test_bool(self, raw, expected):
        r = _resolver(defs=[_def(default=None)],
                      values=[_val(value=raw, rank=1)])
        assert r.resolve('allow_partial_delivery', {}) is expected

    def test_int(self):
        r = _resolver(defs=[_def(value_type='int', default='5')])
        assert r.resolve('allow_partial_delivery', {}) == 5

    def test_decimal(self):
        r = _resolver(defs=[_def(value_type='decimal', default='0.25')])
        assert r.resolve('allow_partial_delivery', {}) == 0.25

    def test_ref_converted_to_int(self):
        r = _resolver(defs=[_def(value_type='ref', default='12',
                                 target_bo='payment_term')])
        assert r.resolve('allow_partial_delivery', {}) == 12

    def test_string_kept_as_is(self):
        r = _resolver(defs=[_def(value_type='string', default='NET30')])
        assert r.resolve('allow_partial_delivery', {}) == 'NET30'

    def test_invalid_raw_falls_back_to_default(self):
        r = _resolver(defs=[_def(value_type='int', default='7')],
                      values=[_val(value='abc', rank=1)])
        assert r.resolve('allow_partial_delivery', {}) == 7

    def test_invalid_raw_without_default_returns_none(self):
        r = _resolver(defs=[_def(value_type='int', default=None)],
                      values=[_val(value='abc', rank=1)])
        assert r.resolve('allow_partial_delivery', {}) is None

    def test_blank_raw_returns_none(self):
        r = _resolver(defs=[_def(default='  ')])
        assert r.resolve('allow_partial_delivery', {}) is None

    def test_enum_kept_as_code(self):
        r = _resolver(defs=[_def(value_type='enum', default='NET30',
                                 enum_type_id=9)])
        assert r.resolve('allow_partial_delivery', {}) == 'NET30'


# ─────────────────────────────────────────────────────────────────────────────
# explain / 缓存
# ─────────────────────────────────────────────────────────────────────────────

class TestExplain:
    def test_explain_reports_hit_row_and_candidates(self):
        r = _resolver(
            defs=[_def(default='true')],
            values=[_val(id=11, value='false', rank=900),
                    _val(id=12, value='true', rank=100, org_id=1)],
        )
        info = r.explain('allow_partial_delivery', {'org_id': 1})
        assert info['value'] is True
        assert info['source'] == {'type': 'value', 'value_id': 12,
                                  'specificity_rank': 100}
        assert [c['value_id'] for c in info['candidates']] == [12, 11]

    def test_explain_reports_default_source(self):
        r = _resolver(defs=[_def(default='true')], values=[])
        info = r.explain('allow_partial_delivery', {})
        assert info['source']['type'] == 'default'
        assert info['candidates'] == []

    def test_explain_missing_definition(self):
        info = _resolver().explain('nope', {})
        assert info['value'] is None
        assert info['source']['type'] == 'missing'


class TestCache:
    def test_invalidate_reloads(self):
        ds = _FakeDS(defs=[_def(default='true')])
        r = ControlParameterResolver(ds)
        assert r.resolve('allow_partial_delivery', {}) is True
        ds.defs = [_def(default='false')]
        assert r.resolve('allow_partial_delivery', {}) is True  # 命中缓存
        r.invalidate()
        assert r.resolve('allow_partial_delivery', {}) is False

    def test_module_level_singleton_is_stable(self):
        assert get_control_parameter_resolver() is get_control_parameter_resolver()
