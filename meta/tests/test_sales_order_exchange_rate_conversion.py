# -*- coding: utf-8 -*-
"""销售订单多币种汇率折算与冻结（C2）

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §3.6/§3.7
      docs/superpowers/specs/2026-10-24-currency-rate-domain/spec.md

覆盖:
  a. 订单 USD + 价目表 CNY：按 `currency_rates` 最新汇率折算并冻结抬头三列
  b. 抬头已有汇率快照：直接复用，不再查 `currency_rates`
  c. 无快照且无汇率行：`failed` / `CURRENCY_MISMATCH`，不按 1:1 折算
  d. 同币种：零回归（不查汇率、trace 无折算标记）
  e. 真实 `PricingDeterminationService`：折算方向 / 2 位保留 / 留痕字段

前半段用假数据源 + 桩服务验证接线；后半段用临时 SQLite 真跑定价确定服务。
"""

from pathlib import Path
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.core.sql_adapters import SQLiteAdapter
from meta.services.pricing_determination_service import (
    REASON_CURRENCY_MISMATCH,
    PricingDeterminationService,
)
from meta.services.sales_order_pricing_service import SalesOrderPricingService
from meta.tests.factories._pricing_w1_helpers import (
    create_pricing_tables,
    seed_rate_table,
    seed_rule,
    seed_row,
)

CNY_ID, USD_ID = 8, 9


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源：只覆盖接线层用到的 SQL 形态
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, orders=None, lines=None, rates=None):
        self.orders = orders or {}
        self.lines = lines or {}
        self.rates = list(rates or [])
        self.queries = []
        self.updates = []

    def query(self, sql, params=None):
        p = list(params or [])
        self.queries.append(sql)
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        if 'FROM sales_order_lines WHERE order_id' in sql:
            rows = [l for l in self.lines.values() if l.get('order_id') == p[0]]
            return sorted(rows, key=lambda l: (str(l.get('line_no')), l.get('id')))
        if 'FROM sales_order_lines WHERE id' in sql:
            row = self.lines.get(p[0])
            return [row] if row else []
        if 'FROM currencies WHERE id' in sql:
            return [{'id': p[0], 'code': {CNY_ID: 'CNY', USD_ID: 'USD'}.get(p[0], 'CNY')}]
        if 'FROM currencies WHERE code' in sql:
            for cid, code in ((CNY_ID, 'CNY'), (USD_ID, 'USD')):
                if code == p[0]:
                    return [{'id': cid}]
            return []
        if 'FROM currency_rates' in sql:
            src, dst, on_date = p[0], p[1], p[2]
            rows = [r for r in self.rates
                    if r['currency_id'] == src and r['to_currency_id'] == dst
                    and r['valid_from'] <= on_date]
            rows.sort(key=lambda r: (r['valid_from'], r.get('id', 0)), reverse=True)
            return rows[:1]
        raise AssertionError('unexpected sql: %s' % sql)

    def execute(self, sql, params=None):
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
    """桩「定价确定服务」：记录入参，返回预设结果。"""

    def __init__(self, resolved=None, result=None):
        self.resolved = resolved if resolved is not None else {
            'matched': True, 'reason': None,
            'rule': {'code': 'PD_STD', 'calc_procedure_id': 1},
            'rate_table': {'id': 1, 'code': 'PL_STD', 'currency': 'CNY'},
            'procedure_code': 'PRICE_STD', 'sequence_code': 'LK_ITEM_STD',
        }
        self.result = result or {
            'pricing_status': 'determined', 'reason': None,
            'unit_price': 100.0, 'amount': 100.0,
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
            'order_date': '2026-10-25', 'price_date': None, 'currency_id': USD_ID,
            'sales_org_id': 318, 'pricing_status': 'pending',
            'exchange_rate': None, 'exchange_rate_type': None,
            'exchange_rate_date': None}
    base.update(overrides)
    return base


def _line(**overrides):
    base = {'id': 100, 'order_id': 10, 'line_no': '1', 'item_id': 2, 'qty': 1,
            'unit_price': None, 'price_source': None, 'price_trace': None,
            'status': 'open'}
    base.update(overrides)
    return base


def _rate_row(rate, valid_from='2026-10-01', rate_id=1,
              src=USD_ID, dst=CNY_ID, rate_type='spot'):
    return {'id': rate_id, 'currency_id': src, 'to_currency_id': dst,
            'rate_type': rate_type, 'valid_from': valid_from, 'rate': rate}


def _calls(det, kind):
    return [k for name, k in det.calls if name == kind]


# ─────────────────────────────────────────────────────────────────────────────
# 接线层：取价时冻结汇率
# ─────────────────────────────────────────────────────────────────────────────

class TestFreezeRateOnPricing:

    def test_cross_currency_freezes_rate_from_currency_rates(self):
        """a. USD 订单 + CNY 价目表：取价时按最新 spot 汇率冻结抬头三列。"""
        ds = _FakeDS(orders={10: _order()}, lines={100: _line()},
                     rates=[_rate_row(7.0, '2026-09-01'),
                            _rate_row(7.1, '2026-10-01', rate_id=2)])
        det = _StubDet()
        got = SalesOrderPricingService(ds, determination=det).price_line(100)

        assert got['pricing_status'] == 'determined'
        # 取最新一条（valid_from 最大）
        assert ds.orders[10]['exchange_rate'] == 7.1
        assert ds.orders[10]['exchange_rate_type'] == 'spot'
        assert ds.orders[10]['exchange_rate_date'] == '2026-10-25'
        assert any(u[0] == 'sales_orders' and u[2].get('exchange_rate') == 7.1
                   for u in ds.updates)

        line_calls = _calls(det, 'determine_line')
        assert line_calls and line_calls[0]['exchange_rate'] == 7.1
        assert line_calls[0]['exchange_rate_type'] == 'spot'
        assert line_calls[0]['exchange_rate_date'] == '2026-10-25'
        # 跨币种必须允许折算，否则拿不到价目表
        assert _calls(det, 'resolve')[0]['allow_currency_conversion'] is True

    def test_existing_snapshot_is_reused_without_querying_rates(self):
        """b. 抬头已冻结汇率：复用快照，不再查 currency_rates。"""
        ds = _FakeDS(orders={10: _order(exchange_rate=7.0,
                                        exchange_rate_type='corporate',
                                        exchange_rate_date='2026-10-01')},
                     lines={100: _line()},
                     rates=[_rate_row(7.1, '2026-10-01')])
        det = _StubDet()
        got = SalesOrderPricingService(ds, determination=det).price_line(100)

        assert got['pricing_status'] == 'determined'
        assert not [q for q in ds.queries if 'FROM currency_rates' in q]
        assert ds.orders[10]['exchange_rate'] == 7.0
        assert ds.orders[10]['exchange_rate_type'] == 'corporate'
        line_calls = _calls(det, 'determine_line')
        assert line_calls and line_calls[0]['exchange_rate'] == 7.0
        assert not [u for u in ds.updates if u[2].get('exchange_rate')]

    def test_missing_rate_does_not_freeze_and_keeps_price(self):
        """c. 无快照且无汇率行：不冻结、不写价，交给定价确定返回失败。"""
        failed = {'pricing_status': 'failed', 'reason': REASON_CURRENCY_MISMATCH,
                  'unit_price': None, 'amount': None,
                  'trace': {'matched_rule_code': None, 'rate_table_code': 'PL_STD',
                            'procedure_code': 'PRICE_STD', 'candidates': 0,
                            'hit_ids': [], 'result_id': None,
                            'reason': REASON_CURRENCY_MISMATCH,
                            'price_currency': 'CNY'}}
        ds = _FakeDS(orders={10: _order()},
                     lines={100: _line(unit_price=700, price_source=None)})
        det = _StubDet(result=failed)
        got = SalesOrderPricingService(ds, determination=det).price_line(100)

        assert got['pricing_status'] == 'failed'
        assert got['reason'] == REASON_CURRENCY_MISMATCH
        assert ds.orders[10]['exchange_rate'] is None
        assert not [u for u in ds.updates if u[0] == 'sales_orders'
                    and u[2].get('exchange_rate')]
        assert ds.lines[100]['unit_price'] == 700          # 原价保留，未按 1:1 改写
        line_calls = _calls(det, 'determine_line')
        assert line_calls and line_calls[0]['exchange_rate'] is None

    def test_same_currency_skips_rate_lookup(self):
        """d. 同币种：不查 currency_rates，不传汇率。"""
        ds = _FakeDS(orders={10: _order(currency_id=CNY_ID)}, lines={100: _line()},
                     rates=[_rate_row(7.1, '2026-10-01')])
        det = _StubDet()
        got = SalesOrderPricingService(ds, determination=det).price_line(100)

        assert got['pricing_status'] == 'determined'
        assert not [q for q in ds.queries if 'FROM currency_rates' in q]
        assert not [q for q in ds.queries if 'FROM currencies WHERE code' in q]
        line_calls = _calls(det, 'determine_line')
        assert line_calls and line_calls[0]['exchange_rate'] is None


# ─────────────────────────────────────────────────────────────────────────────
# 定价确定服务：真实 SQLite
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / 'pricing.db'
    conn = sqlite3.connect(str(path))
    try:
        create_pricing_tables(conn)
    finally:
        conn.close()
    seed_row(path, 'calc_procedures', id=1, code='PRICE_STD', name='标准销售定价过程')
    seed_row(path, 'lookup_sequences', id=1, code='LK_ITEM_STD', name='物料标准查找序列')
    seed_rate_table(path, code='PL_STD', name='标准价目表', currency='CNY')
    seed_rule(path, code='PD_STD', rate_table_id=1)
    return path


@pytest.fixture
def ds(db_path: Path):
    adapter = SQLiteAdapter()
    assert adapter.connect(path=str(db_path))
    yield adapter
    adapter.disconnect()


class _StubPricing:
    def __init__(self, net_amount=700.0):
        self.net_amount = net_amount
        self.calls = []

    def load_candidates(self, rate_table_id, valid_on=None):
        return [1]

    def price_line(self, **kwargs):
        self.calls.append(kwargs)
        return {'hit_ids': [11],
                'result_id': 99 if kwargs.get('persist') else None,
                'net_amount': self.net_amount}


def _determine(ds, **kwargs):
    stub = _StubPricing()
    out = PricingDeterminationService(
        ds, pricing_service=stub).determine_line(item_id=1, **kwargs)
    return out, stub


class TestDetermineLineConversion:

    def test_cross_currency_divides_by_rate_and_traces(self, ds):
        """e. 价目表金额 700 CNY ÷ 7.0 → 100 USD；trace 保留原币金额。"""
        out, _stub = _determine(
            ds, qty=2, price_date='2026-10-25', currency='USD',
            exchange_rate=7.0, exchange_rate_type='spot',
            exchange_rate_date='2026-10-25')

        assert out['pricing_status'] == 'determined'
        assert out['amount'] == 100.0
        assert out['unit_price'] == 50.0
        assert out['trace']['exchange_rate'] == 7.0
        assert out['trace']['exchange_rate_type'] == 'spot'
        assert out['trace']['exchange_rate_date'] == '2026-10-25'
        assert out['trace']['currency_converted'] is True
        assert out['trace']['price_currency'] == 'CNY'
        assert out['trace']['table_amount'] == 700.0
        assert out['trace']['rate_table_code'] == 'PL_STD'

    def test_rounding_two_decimals_half_up(self, ds):
        """折算保留 2 位（ROUND_HALF_UP）：700 / 7.1 = 98.5921… → 98.59。"""
        out, _stub = _determine(
            ds, qty=1, price_date='2026-10-25', currency='USD',
            exchange_rate=7.1)

        assert out['pricing_status'] == 'determined'
        assert out['amount'] == 98.59
        assert out['unit_price'] == 98.59

    def test_missing_rate_fails_currency_mismatch(self, ds):
        """无汇率：失败而非 1:1 静默折算。"""
        out, stub = _determine(ds, qty=1, price_date='2026-10-25', currency='USD')

        assert out['pricing_status'] == 'failed'
        assert out['reason'] == REASON_CURRENCY_MISMATCH
        assert out['trace']['reason'] == REASON_CURRENCY_MISMATCH
        assert out['unit_price'] is None
        assert not stub.calls                       # 未进入取价

    def test_same_currency_zero_regression(self, ds):
        """同币种：金额不变，trace 汇率记 None，无折算标记。"""
        out, _stub = _determine(ds, qty=1, price_date='2026-10-25', currency='CNY')

        assert out['pricing_status'] == 'determined'
        assert out['amount'] == 700.0
        assert out['unit_price'] == 700.0
        assert out['trace']['exchange_rate'] is None
        assert 'currency_converted' not in out['trace']
        assert 'table_amount' not in out['trace']
