# -*- coding: utf-8 -*-
"""销售订单金额测试（W0-R3/R7/R11/R12 + 拦截器回写接线）

依据: meta/schemas/sales_order_line.yaml 头注释「行级口径 ③」
      docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md §1.4
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.action_context import ActionResult
from meta.core.interceptors.sales_order_guard_interceptor import (
    SalesOrderGuardInterceptor,
)
from meta.services.sales_order_amount_service import (
    SalesOrderAmountError,
    SalesOrderAmountService,
)


class _FakeDS:
    """按 SQL 特征片段分流；execute 只记录，不落库。"""

    def __init__(self, line=None, order=None, rows=None, decimals=2,
                 category='standard', rate='13', no_rate=False,
                 raise_on_rate=False, tax_rounding='round'):
        self.line = line
        self.order = order
        self.rows = rows or []
        self.decimals = decimals
        self.category = category
        self.rate = rate
        self.no_rate = no_rate
        self.raise_on_rate = raise_on_rate
        # [D 2026-10-27] 税码舍入方式（tax_code.rounding）——税额舍入按此执行
        self.tax_rounding = tax_rounding
        self.executed = []

    def query(self, sql, params=None):
        if 'FROM sales_order_lines WHERE id' in sql:
            return [self.line] if self.line else []
        if 'FROM sales_orders WHERE id' in sql:
            return [self.order] if self.order else []
        if 'FROM sales_order_lines WHERE order_id' in sql:
            return self.rows
        if 'FROM currencies WHERE id' in sql:
            return [{'decimal_places': self.decimals}]
        if 'FROM type_definitions WHERE id' in sql:
            return [{'document_category': self.category}]
        if 'FROM tax_rates' in sql:
            if self.raise_on_rate:
                raise RuntimeError('db down')
            return [] if self.no_rate else [{'rate_percent': self.rate}]
        # [D 2026-10-27] 税码舍入方式
        if 'FROM tax_codes WHERE id' in sql:
            return [{'rounding': self.tax_rounding}]
        # [M1 2026-10-30] 履约派生统计 SQL（sales_order_fulfillment_service
        #   ._fetch_line_stats，含 delivered_any）——本用例只关心金额回算，
        #   履约统计按空集处理（不触发行级状态回写）。
        if 'LEFT JOIN sales_order_schedules' in sql:
            return []
        raise AssertionError('unexpected sql: %s' % sql)

    def execute(self, sql, params=None):
        self.executed.append((sql, list(params or [])))


ORDER = {'id': 5, 'document_type_id': 1, 'order_date': '2026-10-25', 'currency_id': 8}


def _ds(**kwargs):
    line = kwargs.pop('line', {'id': 9, 'order_id': 5, 'qty': 3,
                               'unit_price': 33.33, 'tax_code_id': 1})
    return _FakeDS(line=line, order=ORDER, **kwargs)


class TestLineAmount:

    def test_rounding_and_tax(self):
        ds = _ds()
        values = SalesOrderAmountService(ds).recompute_line(9)
        assert values['net_amount'] == Decimal('99.99')
        assert values['tax_base_amount'] == Decimal('99.99')
        assert values['tax_rate_percent'] == Decimal('13')
        assert values['tax_amount'] == Decimal('13.00')
        assert values['gross_amount'] == Decimal('112.99')

    def test_write_params_are_float_not_decimal(self):
        ds = _ds()
        SalesOrderAmountService(ds).recompute_line(9)
        sql, params = ds.executed[0]
        assert 'sales_order_lines' in sql
        assert all(isinstance(p, float) for p in params[:5])

    def test_return_document_is_negative(self):
        ds = _ds(category='return')
        values = SalesOrderAmountService(ds).recompute_line(9)
        assert values['net_amount'] == Decimal('-99.99')
        assert values['tax_amount'] == Decimal('-13.00')
        assert values['gross_amount'] == Decimal('-112.99')

    def test_no_tax_code_keeps_tax_zero(self):
        ds = _ds(line={'id': 9, 'order_id': 5, 'qty': 10,
                       'unit_price': 100, 'tax_code_id': None})
        values = SalesOrderAmountService(ds).recompute_line(9)
        assert values['net_amount'] == Decimal('1000.00')
        assert values['tax_rate_percent'] is None
        assert values['tax_amount'] == Decimal('0.00')

    def test_zero_decimal_currency_rounds_half_up(self):
        ds = _ds(decimals=0)
        values = SalesOrderAmountService(ds).recompute_line(9)
        # 3 × 33.33 = 99.99 → 100；13% → 13
        assert values['net_amount'] == Decimal('100')
        assert values['tax_amount'] == Decimal('13')
        assert values['gross_amount'] == Decimal('113')

    def test_missing_rate_raises(self):
        ds = _ds(no_rate=True)
        with pytest.raises(SalesOrderAmountError) as e:
            SalesOrderAmountService(ds).recompute_line(9)
        assert e.value.rule == 'tax_rate_missing'
        assert e.value.field_name == 'tax_code_id'

    def test_missing_line_returns_none(self):
        assert SalesOrderAmountService(_ds(line=None)).recompute_line(9) is None

    def test_missing_order_returns_none(self):
        ds = _ds()
        ds.order = None
        assert SalesOrderAmountService(ds).recompute_line(9) is None


class TestOrderTotals:

    def test_sum_lines(self):
        ds = _ds(rows=[
            {'net_amount': 1000.0, 'tax_amount': 130.0, 'gross_amount': 1130.0},
            {'net_amount': 99.99, 'tax_amount': 13.0, 'gross_amount': 112.99},
        ])
        values = SalesOrderAmountService(ds).recompute_order(5)
        assert values['net_amount'] == Decimal('1099.99')
        assert values['tax_amount'] == Decimal('143.00')
        assert values['gross_amount'] == Decimal('1242.99')

    def test_empty_order_totals_zero(self):
        values = SalesOrderAmountService(_ds(rows=[])).recompute_order(5)
        assert values['net_amount'] == Decimal('0.00')
        assert values['gross_amount'] == Decimal('0.00')


class TestInterceptorAfterAction:

    def _ctx(self, action, ds, result_data=None, old_data=None, extra=None):
        return SimpleNamespace(
            meta_object=SimpleNamespace(id='sales_order_line'),
            action=action,
            object_id=9,
            params={},
            old_data=old_data,
            extra=extra or {},
            data_source=ds,
            result=ActionResult(success=True, data=result_data or {}),
        )

    def test_create_recomputes_line_and_order(self):
        ds = _ds(rows=[
            {'net_amount': 99.99, 'tax_amount': 13.0, 'gross_amount': 112.99},
        ])
        ctx = self._ctx('crud_create', ds, result_data={'id': 9},
                        extra={'so_parent_order_id': 5})
        SalesOrderGuardInterceptor().after_action(ctx)
        assert ctx.result.data['net_amount'] == 99.99
        assert ctx.result.data['gross_amount'] == 112.99
        sqls = [sql for sql, _ in ds.executed]
        assert any('sales_order_lines' in s for s in sqls)
        assert any('sales_orders' in s for s in sqls)

    def test_delete_recomputes_order_from_old_data(self):
        ds = _ds(rows=[])
        ctx = self._ctx('crud_delete', ds, old_data={'order_id': 5})
        SalesOrderGuardInterceptor().after_action(ctx)
        sqls = [sql for sql, _ in ds.executed]
        assert any('sales_orders' in s for s in sqls)
        assert not any('sales_order_lines' in s for s in sqls)

    def test_order_object_skips_recompute(self):
        ds = _ds()
        ctx = self._ctx('crud_create', ds, result_data={'id': 5})
        ctx.meta_object = SimpleNamespace(id='sales_order')
        SalesOrderGuardInterceptor().after_action(ctx)
        assert ds.executed == []


class TestAmountHooks:
    """[D-VI-27 2026-11-12] 内核算术钩子：默认零回归 + 含税倒算路径（VI 复用）。"""

    def _svc(self):
        return SalesOrderAmountService(_FakeDS())

    def test_line_hook_default_path_a_matches_legacy(self):
        values = self._svc()._line_amounts(
            qty=Decimal('3'), unit_price=Decimal('33.33'),
            tax_rate_percent=Decimal('13'), tax_rounding='round',
            decimals=2)
        assert values['net_amount'] == Decimal('99.99')
        assert values['tax_amount'] == Decimal('13.00')
        assert values['gross_amount'] == Decimal('112.99')

    def test_line_hook_path_a_applies_net_adjustment_before_tax(self):
        values = self._svc()._line_amounts(
            qty=Decimal('1'), unit_price=Decimal('100'),
            tax_rate_percent=Decimal('13'), net_adjustment=Decimal('-10'),
            decimals=2)
        assert values['net_amount'] == Decimal('90.00')
        assert values['tax_amount'] == Decimal('11.70')
        assert values['gross_amount'] == Decimal('101.70')

    def test_line_hook_price_includes_tax_back_calculates(self):
        # A2: 3 × 113（含税）@13% → gross 339 / net 300 / tax 39
        values = self._svc()._line_amounts(
            qty=Decimal('3'), unit_price=Decimal('113'),
            price_includes_tax=1, tax_rate_percent=Decimal('13'),
            decimals=2)
        assert values['gross_amount'] == Decimal('339.00')
        assert values['net_amount'] == Decimal('300.00')
        assert values['tax_amount'] == Decimal('39.00')

    def test_line_hook_price_includes_tax_zero_decimal(self):
        # A4: 0 位币种 1 × 1001.4（含税）@13% → gross 1001，net + tax 恒等
        values = self._svc()._line_amounts(
            qty=Decimal('1'), unit_price=Decimal('1001.4'),
            price_includes_tax=True, tax_rate_percent=Decimal('13'),
            decimals=0)
        assert values['gross_amount'] == Decimal('1001')
        assert values['net_amount'] + values['tax_amount'] == Decimal('1001')

    def test_line_hook_without_rate_falls_back_to_path_a(self):
        values = self._svc()._line_amounts(
            qty=Decimal('2'), unit_price=Decimal('50'),
            price_includes_tax=1, tax_rate_percent=None, decimals=2)
        assert values['net_amount'] == Decimal('100.00')
        assert values['tax_amount'] == Decimal('0.00')

    def test_header_hook_default_rounds_three_items(self):
        values = self._svc()._header_amounts(
            sum_net=Decimal('1000.005'), sum_tax=Decimal('130.005'),
            sum_gross=Decimal('1130.01'), decimals=2)
        assert values == {
            'net_amount': Decimal('1000.01'),
            'tax_amount': Decimal('130.01'),
            'gross_amount': Decimal('1130.01'),
        }
