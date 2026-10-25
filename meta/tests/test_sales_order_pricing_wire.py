# -*- coding: utf-8 -*-
"""销售订单定价接线测试（W1-A6）

覆盖: §3.7 触发时点 1/2/3/4/5，§3.8 W1-R1/R2/R3
      含接线层（拦截器触发判定）与服务层（写回 / 降级 / 抬头汇总）。

用假数据源 + 桩「定价确定服务」，不依赖真实定价引擎。
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.interceptors.sales_order_guard_interceptor import (
    SalesOrderGuardInterceptor,
)
from meta.services.sales_order_pricing_service import SalesOrderPricingService


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源：只覆盖金额服务与接线服务用到的 SQL
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, orders=None, lines=None):
        self.orders = orders or {}
        self.lines = lines or {}
        self.updates = []

    def query(self, sql, params=None):
        p = list(params or [])
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        if 'FROM sales_order_lines WHERE order_id' in sql:
            rows = [l for l in self.lines.values() if l.get('order_id') == p[0]]
            return sorted(rows, key=lambda l: (str(l.get('line_no')), l.get('id')))
        if 'FROM sales_order_lines WHERE id' in sql:
            row = self.lines.get(p[0])
            return [{k: row.get(k) for k in (
                'id', 'order_id', 'line_no', 'item_id', 'qty', 'unit_price',
                'price_source', 'price_trace', 'status')}] if row else []
        if 'FROM currencies WHERE id' in sql:
            return [{'id': p[0], 'code': {8: 'CNY', 9: 'USD'}.get(p[0], 'CNY')}]
        if 'FROM type_definitions WHERE id' in sql:
            return [{'id': p[0], 'document_category': 'standard'}]
        if 'FROM tax_rates' in sql:
            return []
        raise AssertionError('unexpected sql: %s' % sql)

    def execute(self, sql, params=None):
        """只实现 UPDATE：按 SET 子句列顺序回写假行。"""
        if not sql.strip().upper().startswith('UPDATE'):
            return
        head, where = sql.split(' WHERE ', 1)
        table = head[len('UPDATE '):].split(' SET ', 1)[0].strip()
        sets = head.split(' SET ', 1)[1]
        cols = [seg.strip().split(' = ')[0] for seg in sets.split(',') if '?' in seg]
        values = list(params or [])
        target = values.pop()
        store = self.orders if table == 'sales_orders' else self.lines
        row = store.get(target)
        if row is None:
            return
        for col, value in zip(cols, values):
            row[col] = value
        self.updates.append((table, target, dict(zip(cols, values))))


class _StubDet:
    """桩「定价确定服务」：记录调用，返回预设结果。"""

    def __init__(self, resolved=None, result=None):
        self.resolved = resolved if resolved is not None else {
            'matched': True, 'reason': None,
            'rule': {'code': 'PD_STD', 'calc_procedure_id': 1},
            'rate_table': {'id': 1, 'code': 'PL_STD'},
            'procedure_code': 'PRICE_STD', 'sequence_code': 'LK_ITEM_STD',
        }
        self.result = result or {
            'pricing_status': 'determined', 'reason': None,
            'unit_price': 12.5, 'amount': 37.5,
            'trace': {'matched_rule_code': 'PD_STD', 'candidates': 1,
                      'hit_ids': [1], 'result_id': 1, 'reason': None},
        }
        self.calls = []

    def resolve(self, **kwargs):
        self.calls.append(('resolve', kwargs))
        return self.resolved

    def determine_line(self, **kwargs):
        self.calls.append(('determine_line', kwargs))
        return self.result


def _order(**overrides):
    base = {'id': 10, 'status': 'draft', 'order_type_id': 1,
            'order_date': '2026-10-25', 'price_date': None, 'currency_id': 8,
            'sales_org_id': 318, 'pricing_status': 'pending'}
    base.update(overrides)
    return base


def _line(**overrides):
    base = {'id': 100, 'order_id': 10, 'line_no': '1', 'item_id': 2, 'qty': 3,
            'unit_price': None, 'price_source': None, 'price_trace': None,
            'status': 'open', 'net_amount': 0, 'tax_base_amount': 0,
            'tax_amount': 0, 'gross_amount': 0}
    base.update(overrides)
    return base


def _service(ds, det):
    return SalesOrderPricingService(ds, determination=det)


# ─────────────────────────────────────────────────────────────────────────────
# 服务层：行取价
# ─────────────────────────────────────────────────────────────────────────────

class TestPriceLine:

    def test_success_writes_unit_price_and_source(self):
        ds = _FakeDS(orders={10: _order()}, lines={100: _line()})
        det = _StubDet()
        got = _service(ds, det).price_line(100)
        assert got['pricing_status'] == 'determined'
        assert ds.lines[100]['unit_price'] == 12.5
        assert ds.lines[100]['price_source'] == 'rate_table'
        assert 'PD_STD' in ds.lines[100]['price_trace']
        # 抬头快照同步回写
        assert ds.orders[10]['price_list_id'] == 1
        assert ds.orders[10]['pricing_procedure_id'] == 1

    def test_customer_account_forwarded_for_customer_price(self):
        """W2-F：客户维度取自行所属抬头，透传给定价确定服务。"""
        ds = _FakeDS(orders={10: _order(customer_account_id=4)},
                     lines={100: _line()})
        det = _StubDet()
        _service(ds, det).price_line(100)

        calls = [k for kind, k in det.calls if kind == 'determine_line']
        assert calls and calls[0]['customer_account_id'] == 4

    def test_manual_line_untouched_without_force(self):
        ds = _FakeDS(orders={10: _order()},
                     lines={100: _line(unit_price=99, price_source='manual')})
        det = _StubDet()
        assert _service(ds, det).price_line(100) is None
        assert not det.calls
        assert ds.lines[100]['unit_price'] == 99

    def test_force_overrides_manual(self):
        ds = _FakeDS(orders={10: _order()},
                     lines={100: _line(unit_price=99, price_source='manual')})
        det = _StubDet()
        _service(ds, det).price_line(100, force=True)
        assert ds.lines[100]['unit_price'] == 12.5
        assert ds.lines[100]['price_source'] == 'rate_table'

    def test_non_draft_skipped(self):
        ds = _FakeDS(orders={10: _order(status='confirmed')}, lines={100: _line()})
        det = _StubDet()
        assert _service(ds, det).price_line(100) is None
        assert not det.calls

    def test_no_item_skipped(self):
        ds = _FakeDS(orders={10: _order()}, lines={100: _line(item_id=None)})
        det = _StubDet()
        assert _service(ds, det).price_line(100) is None

    def test_zero_qty_skipped(self):
        ds = _FakeDS(orders={10: _order()}, lines={100: _line(qty=0)})
        det = _StubDet()
        assert _service(ds, det).price_line(100) is None

    def test_failure_keeps_price_and_writes_reason(self):
        failed = {'pricing_status': 'failed', 'reason': 'NO_CANDIDATE',
                  'unit_price': None, 'amount': None,
                  'trace': {'matched_rule_code': 'PD_STD', 'candidates': 1,
                            'hit_ids': [], 'result_id': None,
                            'reason': 'NO_CANDIDATE'}}
        ds = _FakeDS(orders={10: _order()},
                     lines={100: _line(unit_price=7, price_source=None)})
        got = _service(ds, _StubDet(result=failed)).price_line(100)
        assert got['reason'] == 'NO_CANDIDATE'
        assert ds.lines[100]['unit_price'] == 7          # 原单价保留
        assert ds.lines[100]['price_source'] is None
        assert '"NO_CANDIDATE"' in ds.lines[100]['price_trace']


# ─────────────────────────────────────────────────────────────────────────────
# 服务层：整单重取与抬头汇总
# ─────────────────────────────────────────────────────────────────────────────

class TestRepriceOrder:

    def test_force_reprices_all_open_lines(self):
        ds = _FakeDS(
            orders={10: _order()},
            lines={100: _line(id=100, line_no='1', price_source='manual',
                              unit_price=99),
                   101: _line(id=101, line_no='2')})
        det = _StubDet()
        summary = _service(ds, det).reprice_order(10, force=True)
        assert summary['repriced'] == 2
        assert ds.lines[100]['unit_price'] == 12.5
        assert ds.lines[101]['unit_price'] == 12.5
        assert summary['pricing_status'] == 'determined'

    def test_skips_cancelled_lines(self):
        ds = _FakeDS(orders={10: _order()},
                     lines={100: _line(status='cancelled'),
                            101: _line(id=101, line_no='2')})
        summary = _service(ds, _StubDet()).reprice_order(10, force=True)
        assert summary['repriced'] == 1

    def test_non_draft_returns_none_unless_strict(self):
        ds = _FakeDS(orders={10: _order(status='submitted')}, lines={})
        svc = _service(ds, _StubDet())
        assert svc.reprice_order(10) is None
        with pytest.raises(Exception) as e:
            svc.reprice_order(10, strict=True)
        assert getattr(e.value, 'rule', None) == 'order_not_draft'

    def test_order_not_found_strict(self):
        ds = _FakeDS(orders={}, lines={})
        with pytest.raises(Exception) as e:
            _service(ds, _StubDet()).reprice_order(99, strict=True)
        assert getattr(e.value, 'rule', None) == 'order_not_found'


class TestAggregateStatus:

    @pytest.mark.parametrize('lines,expected', [
        ([], 'pending'),
        ([{'item_id': None}], 'pending'),
        ([{'item_id': 2, 'price_source': 'rate_table', 'price_trace': '{}'}],
         'determined'),
        ([{'item_id': 2, 'price_source': 'manual', 'price_trace': '{}'}], 'manual'),
        ([{'item_id': 2, 'price_source': None,
           'price_trace': '{"reason": "NO_CANDIDATE"}'}], 'failed'),
        # failed 优先于 manual
        ([{'item_id': 2, 'price_source': 'manual', 'price_trace': '{}'},
          {'item_id': 2, 'price_source': None,
           'price_trace': '{"reason": "NO_CANDIDATE"}'}], 'failed'),
        # 有未定价行 → pending
        ([{'item_id': 2, 'price_source': 'rate_table', 'price_trace': '{}'},
          {'item_id': 2, 'price_source': None, 'price_trace': '{}'}], 'pending'),
    ])
    def test_precedence(self, lines, expected):
        assert SalesOrderPricingService._aggregate_status(lines) == expected


# ─────────────────────────────────────────────────────────────────────────────
# 接线层：拦截器触发判定
# ─────────────────────────────────────────────────────────────────────────────

class _RecordingPricing:
    calls = []

    def __init__(self, ds):
        self.ds = ds

    def price_line(self, line_id, **kwargs):
        _RecordingPricing.calls.append(('price_line', line_id, kwargs))
        return None

    def mark_manual(self, line_id):
        _RecordingPricing.calls.append(('mark_manual', line_id, {}))

    def reprice_order(self, order_id, **kwargs):
        _RecordingPricing.calls.append(('reprice_order', order_id, kwargs))
        return {'pricing_status': 'determined', 'net_amount': 37.5,
                'tax_amount': 0, 'gross_amount': 37.5}

    def refresh_order_pricing_status(self, order_id):
        _RecordingPricing.calls.append(('refresh', order_id, {}))
        return 'manual'


def _context(ds, *, object_id, action, params=None, object_id_value=None,
             old_data=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        object_id=object_id_value,
        params=params or {},
        old_data=old_data,
        data_source=ds,
        extra={},
        result=SimpleNamespace(data={}),
    )


@pytest.fixture
def interceptor(monkeypatch):
    import meta.core.interceptors.sales_order_guard_interceptor as mod
    _RecordingPricing.calls = []
    monkeypatch.setattr(mod, 'SalesOrderPricingService', _RecordingPricing)
    return SalesOrderGuardInterceptor()


def _wire_ds():
    return _FakeDS(orders={10: _order()}, lines={100: _line()})


class TestInterceptorTriggers:

    def test_line_create_without_price_auto_prices(self, interceptor):
        ds = _wire_ds()
        ctx = _context(ds, object_id='sales_order_line', action='crud_create',
                       object_id_value=100)
        interceptor.after_action(ctx)
        assert ('price_line', 100, {}) in _RecordingPricing.calls

    def test_line_create_with_price_marks_manual(self, interceptor):
        ds = _wire_ds()
        ctx = _context(ds, object_id='sales_order_line', action='crud_create',
                       object_id_value=100, params={'unit_price': 99})
        interceptor.after_action(ctx)
        assert ('mark_manual', 100, {}) in _RecordingPricing.calls
        assert not any(c[0] == 'price_line' for c in _RecordingPricing.calls)

    def test_line_update_description_only_skips(self, interceptor):
        ds = _wire_ds()
        ctx = _context(ds, object_id='sales_order_line', action='crud_update',
                       object_id_value=100, params={'description': 'x'})
        interceptor.after_action(ctx)
        assert not any(c[0] in ('price_line', 'mark_manual')
                       for c in _RecordingPricing.calls)

    def test_line_update_qty_triggers_reprice(self, interceptor):
        ds = _wire_ds()
        ctx = _context(ds, object_id='sales_order_line', action='crud_update',
                       object_id_value=100, params={'qty': 5})
        interceptor.after_action(ctx)
        assert ('price_line', 100, {}) in _RecordingPricing.calls

    def test_line_update_unit_price_marks_manual(self, interceptor):
        ds = _wire_ds()
        ctx = _context(ds, object_id='sales_order_line', action='crud_update',
                       object_id_value=100, params={'unit_price': 88})
        interceptor.after_action(ctx)
        assert ('mark_manual', 100, {}) in _RecordingPricing.calls

    def test_order_price_date_change_reprices(self, interceptor):
        ds = _wire_ds()
        ctx = _context(ds, object_id='sales_order', action='crud_update',
                       object_id_value=10, params={'price_date': '2026-10-26'})
        interceptor.after_action(ctx)
        assert any(c[0] == 'reprice_order' and c[1] == 10
                   for c in _RecordingPricing.calls)
        assert ctx.result.data['pricing_status'] == 'determined'

    def test_order_other_change_does_not_reprice(self, interceptor):
        ds = _wire_ds()
        ctx = _context(ds, object_id='sales_order', action='crud_update',
                       object_id_value=10, params={'description': 'x'})
        interceptor.after_action(ctx)
        assert not _RecordingPricing.calls
