# -*- coding: utf-8 -*-
"""金额回溯 / 通用重算 测试（只读契约 + 状态门槛）。

覆盖：
  · AmountTraceService：抬头/行漂移、取价来源、定价步骤、调整事实、重算门槛；
  · AmountRecalcService：草稿可重算并落库、非草稿拒绝、未知对象拒绝。

不连真实 DB：FakeDS 按 SQL 特征分流（与 test_sales_order_amount.py 同构）。
"""

from contextlib import contextmanager
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.amount_recalc_service import (
    AmountRecalcError,
    AmountRecalcService,
)
from meta.services.amount_trace_service import AmountTraceService

HEADER = {
    'id': 5,
    'order_no': 'SO-0005',
    'status': 'draft',
    'document_type_id': 1,
    'order_date': '2026-10-25',
    'currency_id': 8,
    'net_amount': 100.0,
    'tax_amount': 13.0,
    'gross_amount': 113.0,
    'header_discount_amount': None,
    'header_surcharge_amount': None,
}

LINE = {
    'id': 9,
    'line_no': 1,
    'order_id': 5,
    'product_code': 'P-001',
    'qty': 3,
    'unit_price': 33.33,
    'tax_code_id': 1,
    'net_amount': 100.0,
    'tax_amount': 13.0,
    'gross_amount': 113.0,
    'price_includes_tax': 0,
    'price_source': 'price_list',
    'price_trace': '{"rule": "price_list_v1", "result_id": 7}',
    'header_discount_amount': None,
    'header_surcharge_amount': None,
}

CALC_RESULT = {
    'id': 7,
    'code': 'PRC-001',
    'document_type': 'sales_order',
    'process_code': 'SO_PRICING',
    'result_semantic': 'net_price',
    'rate_type_code': None,
    'element_type': 'price',
    'price_mode': 'net',
    'status': 'valid',
    'rate': None,
    'base': 3,
    'amount': 99.99,
    'currency': 'CNY',
    'sign': 1,
    'qty_basis': 'qty',
    'fact_snapshot': '{"customer_id": 1}',
}

CALC_STEPS = [
    {'seq': 10, 'element_type': 'base_price', 'price_element_code': 'PB00',
     'rate_type_code': None, 'label': '基准价', 'unit_price': 33.33,
     'extended_amount': 99.99, 'running_net_amount': 99.99, 'base_value': 3,
     'skipped': 0, 'skip_reason': None, 'description': None},
    {'seq': 20, 'element_type': 'discount', 'price_element_code': 'ZD01',
     'rate_type_code': None, 'label': '客户折扣', 'unit_price': 0,
     'extended_amount': 0, 'running_net_amount': 99.99, 'base_value': 99.99,
     'skipped': 1, 'skip_reason': 'no_condition', 'description': None},
]


class _FakeDS:
    """按 SQL 特征片段分流；execute 只记录，不落库。"""

    def __init__(self, header=HEADER, line=LINE, calc=None, steps=None):
        self.header = header
        self.line = line
        self.calc = calc
        self.steps = steps or []
        self.executed = []

    def query(self, sql, params=None):
        if 'FROM sales_orders WHERE id' in sql:
            return [self.header] if self.header else []
        if 'FROM sales_order_lines WHERE order_id' in sql:
            return [self.line] if self.line else []
        if 'FROM sales_order_lines WHERE id' in sql:
            return [self.line] if self.line else []
        if 'FROM currencies WHERE id' in sql:
            return [{'id': 8, 'code': 'CNY', 'decimal_places': 2}]
        if 'FROM type_definitions WHERE id' in sql:
            return [{'document_category': 'standard'}]
        if 'FROM tax_rates' in sql:
            return [{'rate_percent': '13'}]
        if 'FROM tax_codes WHERE id' in sql:
            return [{'id': 1, 'code': 'VAT13', 'name': '13%',
                     'rounding': 'round', 'tax_type': 'output',
                     'tax_treatment': 'standard'}]
        if 'FROM calc_results WHERE id' in sql:
            return [self.calc] if self.calc else []
        if 'FROM calc_results WHERE document_type' in sql:
            return [self.calc] if self.calc else []
        if 'FROM calc_details WHERE result_id' in sql:
            return self.steps
        raise AssertionError('unexpected sql: %s' % sql)

    def execute(self, sql, params=None):
        params = list(params or [])
        self.executed.append((sql, params))
        # 模拟落库，使随后 recompute_order 的「行合计」读到重算后的行值
        if sql.startswith('UPDATE sales_order_lines'):
            self.line = dict(self.line, net_amount=params[0],
                             tax_amount=params[3], gross_amount=params[4])
        elif sql.startswith('UPDATE sales_orders'):
            self.header = dict(self.header, net_amount=params[0],
                               tax_amount=params[1], gross_amount=params[2])

    @contextmanager
    def transaction(self):
        yield


def _ds(**kwargs):
    return _FakeDS(**kwargs)


class TestAmountTrace:

    def test_line_and_header_drift(self):
        ds = _ds()
        data = AmountTraceService(ds).build('sales_order', 5)
        assert data['supported'] is True
        assert data['meta']['readonly'] is True
        assert data['header']['document_no'] == 'SO-0005'
        assert data['header']['decimal_places'] == 2

        line = data['lines'][0]
        # 存储 100.00 vs 内核重算 99.99（qty 3 × 33.33）
        assert line['recomputed']['net_amount'] == 99.99
        assert line['drift']['net_amount'] == pytest.approx(-0.01)
        assert line['price_source'] == 'price_list'
        assert line['price_trace']['rule'] == 'price_list_v1'
        assert line['rounding_label'] == '四舍五入（half-up）'
        assert line['calc'] is None
        # 只读：不产生任何写语句
        assert ds.executed == []

    def test_calc_steps_attached(self):
        data = AmountTraceService(
            _ds(calc=CALC_RESULT, steps=CALC_STEPS)).build('sales_order', 5)
        calc = data['lines'][0]['calc']
        assert calc['process_code'] == 'SO_PRICING'
        assert calc['steps'][0]['price_element_code'] == 'PB00'
        assert calc['steps'][1]['skipped'] == 1

    def test_header_discount_allocation(self):
        line = dict(LINE, header_discount_amount=5)
        data = AmountTraceService(_ds(line=line)).build('sales_order', 5)
        assert data['adjustments']['mode'] == 'header_allocation'
        assert data['lines'][0]['net_adjustment'] == 5.0
        allocated = data['adjustments']['lines']
        assert allocated[-1]['amount'] == 5.0

    def test_recalc_gate_draft_vs_posted(self):
        assert AmountTraceService(_ds()).build('sales_order', 5)['recalc']['allowed']

        posted = dict(HEADER, status='posted')
        data = AmountTraceService(_ds(header=posted)).build('sales_order', 5)
        assert data['recalc']['allowed'] is False
        assert '冻结' in data['recalc']['reason']
        assert data['recalc']['action'] == 'amount.recalc'

    def test_unknown_object_or_missing_record(self):
        assert AmountTraceService(_ds()).build('product', 5) is None
        assert AmountTraceService(_ds(header=None)).build('sales_order', 5) is None


class TestAmountApiContract:
    """统一后端模型：蓝本路由 + BO Action 注册（前端组件依赖这两个契约）。"""

    def test_blueprint_route_registered(self):
        from flask import Flask
        from meta.api.amount_trace_api import amount_trace_bp

        app = Flask(__name__)
        app.register_blueprint(amount_trace_bp)
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert '/api/v2/bo/<object_type>/<record_id>/amount-trace' in rules

    def test_amount_recalc_action_registered(self):
        from meta.core.bo_action_registry import bo_action_registry
        from meta.services.bo_action_registrations import register_all_bo_actions

        register_all_bo_actions(bo_action_registry)
        meta = bo_action_registry.get('amount.recalc')
        assert meta is not None
        assert meta.object_type == '*'
        assert meta.category == 'amount'


class TestAmountRecalc:

    def test_draft_recalc_writes_lines_and_header(self):
        ds = _ds()
        result = AmountRecalcService(ds).recalc('sales_order', 5)
        assert result['line_count'] == 1
        assert result['header']['net_amount'] == 99.99
        sqls = [sql for sql, _ in ds.executed]
        assert any(sql.startswith('UPDATE sales_order_lines') for sql in sqls)
        assert any(sql.startswith('UPDATE sales_orders') for sql in sqls)

    def test_posted_recalc_rejected(self):
        ds = _ds(header=dict(HEADER, status='posted'))
        with pytest.raises(AmountRecalcError) as exc:
            AmountRecalcService(ds).recalc('sales_order', 5)
        assert exc.value.rule == 'AMOUNT_RECALC_STATE_INVALID'
        assert ds.executed == []

    def test_unsupported_object_rejected(self):
        with pytest.raises(AmountRecalcError) as exc:
            AmountRecalcService(_ds()).recalc('product', 5)
        assert exc.value.rule == 'AMOUNT_RECALC_UNSUPPORTED'