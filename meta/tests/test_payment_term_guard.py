# -*- coding: utf-8 -*-
"""付款条件模型与守卫测试（schema 接线 + G1 上限 / G3 / G4 + 拦截器接线）

依据: meta/schemas/payment_term.yaml / payment_term_line.yaml 头注释
"""

import pytest

pytestmark = pytest.mark.unit

from types import SimpleNamespace

import yaml

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.payment_term_guard_interceptor import (
    PaymentTermGuardInterceptor,
)
from meta.services.payment_term_guard_service import (
    PaymentTermGuardError,
    PaymentTermGuardService,
)


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源（只实现守卫用到的一条 SQL 形态）
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, lines=None, raise_on_query=False):
        self.lines = lines or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params):
        assert 'FROM payment_term_lines' in sql
        if self.raise_on_query:
            raise RuntimeError('db down')
        term_id, exclude = params[0], (params[1] if len(params) > 1 else None)
        rows = []
        for row in self.lines:
            if str(row['payment_term_id']) != str(term_id):
                continue
            if exclude is not None and str(row['id']) == str(exclude):
                continue
            rows.append(row)
        return rows


def _svc(lines=None, **kw):
    return PaymentTermGuardService(_FakeDS(lines=lines or [], **kw))


# ─────────────────────────────────────────────────────────────────────────────
# G1 —— 占比合计：写时只拦「超过 100」，完整性由 assert_term_complete 校验
# ─────────────────────────────────────────────────────────────────────────────

class TestPercentageSum:
    def test_rejects_over_100(self):
        svc = _svc([{'id': 1, 'payment_term_id': 10, 'percentage': 60}])
        with pytest.raises(PaymentTermGuardError) as e:
            svc.validate_line_write(
                {'payment_term_id': 10, 'percentage': 50, 'offset_days': 30})
        assert e.value.rule == 'percentage_over_100'
        assert e.value.field_name == 'percentage'

    def test_accepts_exactly_100(self):
        svc = _svc([{'id': 1, 'payment_term_id': 10, 'percentage': 60}])
        svc.validate_line_write(
            {'payment_term_id': 10, 'percentage': 40, 'offset_days': 30})

    def test_allows_incremental_first_line(self):
        # 子表逐行保存：首期 50% 必须先能落库，否则两期条款永远建不出来
        _svc().validate_line_write(
            {'payment_term_id': 20, 'percentage': 50, 'offset_days': 30})

    def test_update_excludes_self(self):
        svc = _svc([{'id': 1, 'payment_term_id': 10, 'percentage': 60}])
        svc.validate_line_write(
            {'id': 1, 'payment_term_id': 10, 'percentage': 100}, exclude_id=1)

    def test_query_failure_fails_open(self):
        _svc(raise_on_query=True).validate_line_write(
            {'payment_term_id': 10, 'percentage': 50})

    def test_assert_complete_passes_on_100(self):
        svc = _svc([{'id': 1, 'payment_term_id': 10, 'percentage': 60},
                    {'id': 2, 'payment_term_id': 10, 'percentage': 40}])
        svc.assert_term_complete(10)

    def test_assert_complete_rejects_partial(self):
        svc = _svc([{'id': 1, 'payment_term_id': 10, 'percentage': 60}])
        with pytest.raises(PaymentTermGuardError) as e:
            svc.assert_term_complete(10)
        assert e.value.rule == 'percentage_not_100'


# ─────────────────────────────────────────────────────────────────────────────
# G3 —— 折扣率与折扣天数成对
# ─────────────────────────────────────────────────────────────────────────────

class TestDiscountPair:
    def _base(self):
        return {'payment_term_id': 10, 'percentage': 100, 'offset_days': 30}

    def test_rejects_percent_without_days(self):
        data = {**self._base(), 'discount_percent': 2}
        with pytest.raises(PaymentTermGuardError) as e:
            _svc().validate_line_write(data)
        assert e.value.rule == 'discount_pair_mismatch'
        assert e.value.field_name == 'discount_days'

    def test_rejects_days_without_percent(self):
        data = {**self._base(), 'discount_days': 10}
        with pytest.raises(PaymentTermGuardError) as e:
            _svc().validate_line_write(data)
        assert e.value.rule == 'discount_pair_mismatch'
        assert e.value.field_name == 'discount_percent'

    def test_accepts_pair(self):
        _svc().validate_line_write(
            {**self._base(), 'discount_percent': 2, 'discount_days': 10})


# ─────────────────────────────────────────────────────────────────────────────
# G4 —— 折扣天数早于到期天数
# ─────────────────────────────────────────────────────────────────────────────

class TestDiscountBeforeMaturity:
    def test_rejects_discount_not_earlier(self):
        data = {'payment_term_id': 10, 'percentage': 100,
                'offset_days': 30, 'discount_percent': 2, 'discount_days': 30}
        with pytest.raises(PaymentTermGuardError) as e:
            _svc().validate_line_write(data)
        assert e.value.rule == 'discount_not_before_maturity'

    def test_accepts_discount_earlier(self):
        _svc().validate_line_write(
            {'payment_term_id': 10, 'percentage': 100,
             'offset_days': 30, 'discount_percent': 2, 'discount_days': 10})

    def test_month_offset_counts_as_thirty_days(self):
        _svc().validate_line_write(
            {'payment_term_id': 10, 'percentage': 100,
             'offset_months': 1, 'offset_days': 0,
             'discount_percent': 2, 'discount_days': 15})

    def test_fixed_day_skips_comparison(self):
        # 有固定日时到期日依赖具体月份，写时不可判定 ⇒ 不拦
        _svc().validate_line_write(
            {'payment_term_id': 10, 'percentage': 100,
             'offset_months': 1, 'fixed_day_of_month': 15, 'offset_days': 0,
             'discount_percent': 2, 'discount_days': 999})


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(object_id, action, params, old_data=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        object_id=params.get('id'),
        data_source=_FakeDS(),
    )


class TestInterceptor:
    def test_priority(self):
        assert PaymentTermGuardInterceptor().priority == 44

    def test_only_guards_line_writes(self):
        ic = PaymentTermGuardInterceptor()
        assert ic.should_execute(_ctx('payment_term_line', 'crud_create', {}))
        assert ic.should_execute(_ctx('payment_term_line', 'crud_update', {}))
        assert not ic.should_execute(_ctx('payment_term_line', 'crud_delete', {}))
        assert not ic.should_execute(_ctx('payment_term', 'crud_create', {}))

    def test_raises_validation_failed(self):
        ic = PaymentTermGuardInterceptor()
        ctx = _ctx('payment_term_line', 'crud_create',
                   {'payment_term_id': 10, 'percentage': 100,
                    'discount_percent': 2})
        with pytest.raises(ValidationFailedError):
            ic.before_action(ctx)

    def test_update_merges_old_data(self):
        ic = PaymentTermGuardInterceptor()
        ctx = _ctx('payment_term_line', 'crud_update',
                   {'id': 1, 'percentage': 100},
                   old_data={'id': 1, 'payment_term_id': 10,
                             'offset_days': 30,
                             'discount_percent': 2, 'discount_days': 10})
        ic.before_action(ctx)  # 合并后折扣成对、合计 100 ⇒ 放行


# ─────────────────────────────────────────────────────────────────────────────
# Schema 接线
# ─────────────────────────────────────────────────────────────────────────────

def _load(name):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'schemas' / f'{name}.yaml'
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestSchema:
    def test_head(self):
        head = _load('payment_term')
        assert head['table_name'] == 'payment_terms'
        assert head['semantics']['business_key'] == ['code']
        assert head['deletion_policy']['restrict_on'][0]['table'] == 'payment_term_lines'
        children = [c['child_object'] for c in head['ui_view_config']['child_sections']]
        assert children == ['payment_term_line']

    def test_line(self):
        line = _load('payment_term_line')
        assert line['parent_object'] == 'payment_term'
        assert line['hierarchy']['parent_field'] == 'payment_term_id'
        assert line['ui_view_config']['skip_auto_menu'] is True
        assert {'fields': ['payment_term_id', 'seq'], 'unique': True,
                'name': 'idx_payment_term_line_seq'} in line['indexes']
