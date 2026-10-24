# -*- coding: utf-8 -*-
"""币种汇率守卫测试（R1 / R2 / R3 / R4 + 拦截器接线）

依据: docs/superpowers/specs/2026-10-24-currency-rate-domain/spec.md §3 / §9.3
"""

import pytest

pytestmark = pytest.mark.unit

from types import SimpleNamespace

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.currency_rate_guard_interceptor import (
    CurrencyRateGuardInterceptor,
)
from meta.core.metadata_driven_validator import MetadataDrivenValidator
from meta.core.models import FieldType, MetaField
from meta.services.currency_rate_guard_service import (
    CurrencyRateGuardError,
    CurrencyRateGuardService,
)


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源（只实现守卫用到的两条 SQL 形态）
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, currencies=None, rates=None, raise_on_query=False):
        self.currencies = currencies or {}
        self.rates = rates or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params):
        if self.raise_on_query:
            raise RuntimeError('db down')
        if 'FROM currencies' in sql:
            row = self.currencies.get(params[0])
            return [row] if row else []
        if 'FROM currency_rates' in sql and 'COUNT(*)' in sql:
            rate_type, valid_from = params[0], params[1]
            a, b, c, d = params[2], params[3], params[4], params[5]
            exclude = params[6] if len(params) > 6 else None
            cnt = 0
            for r in self.rates:
                if r['rate_type'] != rate_type or r['valid_from'] != valid_from:
                    continue
                if exclude is not None and str(r['id']) == str(exclude):
                    continue
                same = (r['currency_id'] == a and r['to_currency_id'] == b)
                mirror = (r['currency_id'] == c and r['to_currency_id'] == d)
                if same or mirror:
                    cnt += 1
            return [{'cnt': cnt}]
        raise AssertionError(f'未预期的 SQL: {sql}')


USD = {'id': 1, 'code': 'USD', 'status': 'active'}
CNY = {'id': 2, 'code': 'CNY', 'status': 'active'}
JPY_OFF = {'id': 3, 'code': 'JPY', 'status': 'inactive'}
CURRENCIES = {1: USD, 2: CNY, 3: JPY_OFF}

BASE_ROW = {
    'id': 1, 'rate_type': 'spot', 'valid_from': '2026-10-01',
    'currency_id': 1, 'to_currency_id': 2,
}


def _svc(rates=None, **kw):
    return CurrencyRateGuardService(_FakeDS(currencies=CURRENCIES, rates=rates or [], **kw))


def _ctx(object_id, action, params, old_data=None, ds=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        object_id=params.get('id'),
        data_source=ds or _FakeDS(currencies=CURRENCIES),
    )


# ─────────────────────────────────────────────────────────────────────────────
# R1 —— 禁止自反
# ─────────────────────────────────────────────────────────────────────────────

class TestSelfPair:
    def test_rejects_same_currency(self):
        with pytest.raises(CurrencyRateGuardError) as e:
            _svc().validate_rate_write(
                {'currency_id': 1, 'to_currency_id': 1,
                 'rate_type': 'spot', 'valid_from': '2026-10-01'})
        assert e.value.rule == 'self_pair'

    def test_accepts_distinct_currencies(self):
        _svc().validate_rate_write(
            {'currency_id': 1, 'to_currency_id': 2,
             'rate_type': 'spot', 'valid_from': '2026-10-01'})


# ─────────────────────────────────────────────────────────────────────────────
# R3 —— 双币种须启用
# ─────────────────────────────────────────────────────────────────────────────

class TestCurrencyActive:
    def test_rejects_inactive_source(self):
        with pytest.raises(CurrencyRateGuardError) as e:
            _svc().validate_rate_write(
                {'currency_id': 3, 'to_currency_id': 2,
                 'rate_type': 'spot', 'valid_from': '2026-10-01'})
        assert e.value.rule == 'currency_inactive'
        assert 'JPY' in str(e.value)

    def test_rejects_inactive_target(self):
        with pytest.raises(CurrencyRateGuardError) as e:
            _svc().validate_rate_write(
                {'currency_id': 1, 'to_currency_id': 3,
                 'rate_type': 'spot', 'valid_from': '2026-10-01'})
        assert e.value.rule == 'currency_inactive'
        assert e.value.field_name == '目标币种'

    def test_unknown_currency_defers_to_fk_check(self):
        # 取不到币种行时不在守卫内报错，交给 FK 存在性校验
        _svc().validate_rate_write(
            {'currency_id': 99, 'to_currency_id': 2,
             'rate_type': 'spot', 'valid_from': '2026-10-01'})


# ─────────────────────────────────────────────────────────────────────────────
# R2 —— 同日镜像行 / 重复方向
# ─────────────────────────────────────────────────────────────────────────────

class TestMirrorPair:
    def test_rejects_reverse_row_same_day(self):
        svc = _svc([BASE_ROW])
        with pytest.raises(CurrencyRateGuardError) as e:
            svc.validate_rate_write(
                {'currency_id': 2, 'to_currency_id': 1,
                 'rate_type': 'spot', 'valid_from': '2026-10-01'})
        assert e.value.rule == 'mirror_pair'

    def test_rejects_duplicate_same_direction(self):
        svc = _svc([BASE_ROW])
        with pytest.raises(CurrencyRateGuardError) as e:
            svc.validate_rate_write(
                {'currency_id': 1, 'to_currency_id': 2,
                 'rate_type': 'spot', 'valid_from': '2026-10-01'})
        assert e.value.rule == 'mirror_pair'

    def test_allows_reverse_row_on_another_day(self):
        svc = _svc([BASE_ROW])
        svc.validate_rate_write(
            {'currency_id': 2, 'to_currency_id': 1,
             'rate_type': 'spot', 'valid_from': '2026-10-02'})

    def test_allows_same_pair_under_another_rate_type(self):
        svc = _svc([BASE_ROW])
        svc.validate_rate_write(
            {'currency_id': 2, 'to_currency_id': 1,
             'rate_type': 'corporate', 'valid_from': '2026-10-01'})

    def test_update_excludes_itself(self):
        svc = _svc([BASE_ROW])
        svc.validate_rate_write(
            {'currency_id': 1, 'to_currency_id': 2,
             'rate_type': 'spot', 'valid_from': '2026-10-01'},
            exclude_id=1)

    def test_update_colliding_with_other_row_raises(self):
        other = {**BASE_ROW, 'id': 2, 'currency_id': 2, 'to_currency_id': 1}
        svc = _svc([BASE_ROW, other])
        # 把 id=3 的行改成与 id=1 同日同币对
        with pytest.raises(CurrencyRateGuardError):
            svc.validate_rate_write(
                {'currency_id': 1, 'to_currency_id': 2,
                 'rate_type': 'spot', 'valid_from': '2026-10-01'},
                exclude_id=3)

    def test_defaults_rate_type_to_spot(self):
        svc = _svc([BASE_ROW])
        with pytest.raises(CurrencyRateGuardError):
            svc.validate_rate_write(
                {'currency_id': 2, 'to_currency_id': 1,
                 'valid_from': '2026-10-01'})

    def test_date_object_is_normalized(self):
        import datetime
        svc = _svc([BASE_ROW])
        with pytest.raises(CurrencyRateGuardError):
            svc.validate_rate_write(
                {'currency_id': 2, 'to_currency_id': 1, 'rate_type': 'spot',
                 'valid_from': datetime.date(2026, 10, 1)})


# ─────────────────────────────────────────────────────────────────────────────
# NFR-001 —— 查询失败 fail-open
# ─────────────────────────────────────────────────────────────────────────────

class TestFailOpen:
    def test_query_failure_does_not_block_write(self):
        svc = _svc(raise_on_query=True)
        svc.validate_rate_write(
            {'currency_id': 1, 'to_currency_id': 2,
             'rate_type': 'spot', 'valid_from': '2026-10-01'})


# ─────────────────────────────────────────────────────────────────────────────
# R4 —— 字段级数值范围 / 小数位（YAML constraints 驱动）
# ─────────────────────────────────────────────────────────────────────────────

class TestRateNumericRange:
    @staticmethod
    def _rate_field():
        return MetaField(
            id='rate', name='汇率', field_type=FieldType.FLOAT,
            db_column='rate', required=True,
            constraints=[{'type': 'numeric_range', 'gt': 0, 'decimal_places': 12}],
        )

    def test_accepts_positive_rate(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._rate_field(), 7.08, '汇率')
        assert errors == []

    def test_rejects_zero_and_negative(self):
        for value in (0, -1):
            errors = MetadataDrivenValidator(None)._check_numeric_range(
                self._rate_field(), value, '汇率')
            assert len(errors) == 1
            assert errors[0].rule == 'numeric_range.gt'

    def test_rejects_thirteen_decimal_places(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._rate_field(), 0.1234567890123, '汇率')
        assert len(errors) == 1
        assert errors[0].rule == 'numeric_range.decimal_places'

    def test_accepts_twelve_decimal_places(self):
        errors = MetadataDrivenValidator(None)._check_numeric_range(
            self._rate_field(), 0.123456789012, '汇率')
        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线（对象 / 动作门控 + 异常转换 + 更新合并）
# ─────────────────────────────────────────────────────────────────────────────

class TestInterceptorWiring:
    def setup_method(self):
        self.itc = CurrencyRateGuardInterceptor()

    def test_only_currency_rate_writes_pass(self):
        assert self.itc.should_execute(_ctx('currency_rate', 'crud_create', {}))
        assert self.itc.should_execute(_ctx('currency_rate', 'crud_update', {}))

    def test_other_objects_and_reads_short_circuit(self):
        assert not self.itc.should_execute(_ctx('currency', 'crud_create', {}))
        assert not self.itc.should_execute(_ctx('currency_rate', 'crud_read', {}))
        assert not self.itc.should_execute(_ctx('currency_rate', 'crud_list', {}))

    def test_mirror_create_raises_validation_failed(self):
        ds = _FakeDS(currencies=CURRENCIES, rates=[BASE_ROW])
        with pytest.raises(ValidationFailedError) as e:
            self.itc.before_action(
                _ctx('currency_rate', 'crud_create',
                     {'currency_id': 2, 'to_currency_id': 1,
                      'rate_type': 'spot', 'valid_from': '2026-10-01'}, ds=ds))
        assert '镜像' not in str(e.value)  # 提示语面向业务，不暴露内部规则名
        assert e.value.details[0]['rule'] == 'mirror_pair'

    def test_update_merges_old_data(self):
        """更新只传 to_currency_id 时，currency_id 由旧行补齐后仍能判定。"""
        ds = _FakeDS(currencies=CURRENCIES, rates=[BASE_ROW])
        with pytest.raises(ValidationFailedError):
            self.itc.before_action(
                _ctx('currency_rate', 'crud_update',
                     {'id': 1, 'to_currency_id': 1},
                     old_data={'id': 1, 'currency_id': 1, 'to_currency_id': 2,
                               'rate_type': 'spot', 'valid_from': '2026-10-01'},
                     ds=ds))

    def test_update_without_identity_fields_is_noop(self):
        ds = _FakeDS(currencies=CURRENCIES, rates=[BASE_ROW])
        self.itc.before_action(
            _ctx('currency_rate', 'crud_update', {'id': 1, 'rate': 7.1}, ds=ds))
