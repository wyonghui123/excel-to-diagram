# -*- coding: utf-8 -*-
"""销售订单抬头折扣 / 附加费测试（spec §4.10 / §6 V-B1 ~ V-B10）

依据: docs/superpowers/specs/2026-10-26-sales-order-billing-and-header-discount-spec.md
      §4.1 不变量 / §4.5 分摊 / §4.6 幂等 / §4.7 留痕 / §4.8 守卫 / §4.10 测试

覆盖:
  · 纯算法 plan 守恒（含 1 分尾差落位）
  · 金额服务叠加两调整列，改 qty 重算后调整额不被覆盖
  · 退货单符号还原（折扣调整为正、附加费调整为负）
  · 零基额确认时拦截 HEADER_DISCOUNT_ZERO_BASE
  · 守卫：率越界 / 折后整单为负 / 非草稿改率 / 快照符号错误
  · 幂等：apply 两次结果行数不翻倍
  · 守恒：Σ 行调整额 = -D，Σ 行净额 = 头 calc_result 末行净额
  · 回放：process_code + allocation_rule_id 两跳还原每行摊得额（parent_id 双层）
"""

import os
from decimal import Decimal

# 本文件的 INSERT / UPDATE / DELETE 仅出现在内存 fake data_source 里，
# 不触碰真实库；按项目惯例显式解除 raw-SQL 守卫（同 test_allocation_by_rule.py）。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest  # noqa: E402

pytestmark = pytest.mark.unit

from meta.services.allocation_service import plan
from meta.services.sales_order_amount_service import SalesOrderAmountService
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)
from meta.services.sales_order_header_discount_service import (
    SalesOrderHeaderDiscountService,
)

RULE = {
    'id': 7,
    'code': 'AR_HDR_DISC_BY_NET',
    'basis': 'value',
    'rounding': 'round',
    'target': 'cost',
}


class _WriteResult:
    """模拟 sqlite cursor：execute 后取 lastrowid / rowcount。"""

    def __init__(self, lastrowid=None, rowcount=0):
        self.lastrowid = lastrowid
        self.rowcount = rowcount


class _FakeDS:
    """内存 fake：query 按 SQL 特征片段分流，execute 落内存表并返回 lastrowid。

    抬头折扣 apply 会串起三个服务（抬头折扣 / 金额 / 分摊留痕），
    故本 fake 同时覆盖它们的查询与写入，而非只记录 SQL。
    """

    def __init__(self, order, lines, category='standard',
                 tax_rate=Decimal('10')):
        self.orders = {order['id']: dict(order)}
        self.lines = {line['id']: dict(line) for line in lines}
        self.category = category
        self.tax_rate = tax_rate
        self.calc_results = []
        self.allocation_results = []
        self._calc_id = 0
        self._alloc_id = 0

    # ---------------- query ----------------

    def query(self, sql, params=None):
        p = list(params or [])

        if 'FROM sales_order_lines WHERE id' in sql:
            row = self.lines.get(int(p[0]))
            return [dict(row)] if row else []
        if 'FROM sales_order_lines WHERE order_id' in sql:
            rows = [dict(r) for r in self.lines.values()
                    if r.get('order_id') == p[0]]
            rows.sort(key=lambda r: (r.get('line_no') or 0, r.get('id')))
            return rows
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(int(p[0]))
            return [dict(row)] if row else []
        if 'FROM currencies WHERE id' in sql:
            return [{'id': p[0], 'code': 'CNY', 'decimal_places': 2}]
        if 'FROM type_definitions WHERE id' in sql:
            return [{'document_category': self.category}]
        if 'FROM tax_rates' in sql:
            return [{'rate_percent': self.tax_rate}]
        if 'FROM calc_procedures WHERE code' in sql:
            return [{'result_semantic': 'price'}]
        if 'FROM allocation_rules WHERE code' in sql:
            return [dict(RULE)]
        if 'SELECT id, sequence FROM calc_results' in sql:
            rows = [{'id': r['id'], 'sequence': r['sequence']}
                    for r in self.calc_results
                    if r['level'] == 'header'
                    and r['document_id'] == p[1]
                    and r['process_code'] == p[2]]
            return rows
        raise AssertionError('unexpected sql: %s' % sql)

    # ---------------- execute ----------------

    def execute(self, sql, params=None):
        p = list(params or [])
        head = sql.lstrip().upper()

        if head.startswith('INSERT INTO CALC_RESULTS'):
            self._calc_id += 1
            self.calc_results.append({
                'id': self._calc_id,
                'code': p[0],
                'document_type': p[1],
                'document_id': p[2],
                'level': p[4],
                'process_code': p[5],
                'amount': p[14],
                'net_amount': p[15],
                'sign': p[17],
                'sequence': p[18],
                'origin': p[19],
            })
            return _WriteResult(lastrowid=self._calc_id, rowcount=1)

        if head.startswith('DELETE FROM CALC_RESULTS'):
            before = len(self.calc_results)
            self.calc_results = [
                r for r in self.calc_results
                if not (r['document_type'] == p[0]
                        and r['document_id'] == p[1]
                        and r['level'] == 'header'
                        and r['process_code'] == p[2])
            ]
            return _WriteResult(rowcount=before - len(self.calc_results))

        if head.startswith('INSERT INTO ALLOCATION_RESULTS'):
            self._alloc_id += 1
            self.allocation_results.append({
                'id': self._alloc_id,
                'code': p[0],
                'document_type': p[1],
                'document_id': p[2],
                'document_line_id': p[3],
                'parent_id': p[4],
                'level': p[5],
                'sequence': p[6],
                'amount': p[7],
                'net_amount': p[8],
                'currency': p[9],
                'sign': p[10],
                'allocation_rule_id': p[11],
                'origin': p[17],
                'target': p[21],
            })
            return _WriteResult(lastrowid=self._alloc_id, rowcount=1)

        if head.startswith('DELETE FROM ALLOCATION_RESULTS'):
            before = len(self.allocation_results)
            self.allocation_results = [
                r for r in self.allocation_results
                if not (r['document_type'] == p[0]
                        and r['document_id'] == p[1]
                        and r['origin'] == 'planned')
            ]
            return _WriteResult(rowcount=before - len(self.allocation_results))

        if head.startswith('UPDATE ALLOCATION_RESULTS'):
            for r in self.allocation_results:
                if (r['level'] == 'line'
                        and r['document_type'] == p[1]
                        and r['document_id'] == p[2]
                        and r['parent_id'] == p[3]
                        and r['origin'] == 'planned'):
                    r['parent_id'] = p[0]
            return _WriteResult(rowcount=0)

        if 'UPDATE sales_order_lines SET header_discount_amount' in sql:
            line = self.lines.get(int(p[2]))
            line['header_discount_amount'] = p[0]
            line['header_surcharge_amount'] = p[1]
            return _WriteResult(rowcount=1)

        if 'UPDATE sales_order_lines SET net_amount' in sql:
            line = self.lines.get(int(p[5]))
            line['net_amount'] = p[0]
            line['tax_base_amount'] = p[1]
            line['tax_rate_percent'] = p[2]
            line['tax_amount'] = p[3]
            line['gross_amount'] = p[4]
            return _WriteResult(rowcount=1)

        if 'UPDATE sales_orders SET header_discount_amount' in sql:
            order = self.orders.get(int(p[2]))
            order['header_discount_amount'] = p[0]
            order['header_surcharge_amount'] = p[1]
            return _WriteResult(rowcount=1)

        if 'UPDATE sales_orders SET net_amount' in sql:
            order = self.orders.get(int(p[3]))
            order['net_amount'] = p[0]
            order['tax_amount'] = p[1]
            order['gross_amount'] = p[2]
            return _WriteResult(rowcount=1)

        raise AssertionError('unexpected sql: %s' % sql)


def _dec(value):
    return Decimal(str(value))


def _order(order_id=5, *, order_type_id=1, discount=0, surcharge=0):
    return {
        'id': order_id,
        'order_type_id': order_type_id,
        'order_date': '2026-10-25',
        'currency_id': 8,
        'header_discount_percent': discount,
        'header_surcharge_percent': surcharge,
        'net_amount': 0,
        'tax_amount': 0,
        'gross_amount': 0,
    }


def _line(line_id, *, net=Decimal('1000'), qty=1, unit_price=1000,
          tax_code_id=1, order_id=5):
    return {
        'id': line_id,
        'order_id': order_id,
        'line_no': line_id,
        'qty': qty,
        'unit_price': Decimal(str(unit_price)),
        'tax_code_id': tax_code_id,
        'net_amount': Decimal(str(net)),
        'header_discount_amount': Decimal('0'),
        'header_surcharge_amount': Decimal('0'),
    }


def _ds(discount=0, surcharge=0, *, lines=None, category='standard'):
    return _FakeDS(
        _order(discount=discount, surcharge=surcharge),
        lines if lines is not None else [_line(11), _line(12)],
        category=category,
    )


def _sum(rows, field):
    return sum((_dec(row[field]) for row in rows), Decimal('0'))


# ---------------- 1. 纯算法 ----------------

def test_plan_conservation_with_cent_remainder():
    """纯算法：最大余数法按权重分摊，1 分尾差自动落位且 Σ 精确等于 D。"""
    values = plan(Decimal('100'),
                  [Decimal('333.33'), Decimal('333.33'), Decimal('333.34')],
                  scale=2, rounding='round')
    assert values == [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')]
    assert sum(values, Decimal('0')) == Decimal('100.00')


# ---------------- 2. 金额服务 ----------------

def test_amount_service_keeps_header_adjustments():
    """金额服务：两侧调整列计入净额，改 qty 重算后调整额仍在（防覆盖）。"""
    line = _line(9, net=Decimal('99.99'), qty=3, unit_price=Decimal('33.33'))
    line['header_discount_amount'] = Decimal('-5')
    line['header_surcharge_amount'] = Decimal('2')
    ds = _ds(lines=[line])
    service = SalesOrderAmountService(ds)

    first = service.recompute_line(9)
    assert first['net_amount'] == Decimal('96.99')
    assert first['tax_amount'] == Decimal('9.70')
    assert first['gross_amount'] == Decimal('106.69')

    ds.lines[9]['qty'] = 4
    second = service.recompute_line(9)
    assert second['net_amount'] == Decimal('130.32')
    assert second['tax_amount'] == Decimal('13.03')
    assert second['gross_amount'] == Decimal('143.35')
    assert _dec(ds.lines[9]['header_discount_amount']) == Decimal('-5')
    assert _dec(ds.lines[9]['header_surcharge_amount']) == Decimal('2')


# ---------------- 3. 退货符号 ----------------

def test_return_order_flips_adjustment_sign():
    """退货单：基额为负，折扣调整为正、附加费调整为负，Σ 行调整 = -D / +S。"""
    ds = _ds(5, 3, category='return', lines=[
        _line(11, net=Decimal('-1000')), _line(12, net=Decimal('-1000'))])
    SalesOrderHeaderDiscountService(ds).apply(5)

    assert _dec(ds.lines[11]['header_discount_amount']) == Decimal('50')
    assert _dec(ds.lines[11]['header_surcharge_amount']) == Decimal('-30')
    assert _dec(ds.lines[11]['net_amount']) == Decimal('-980')
    assert _sum(ds.lines.values(), 'header_discount_amount') == Decimal('100')
    assert _sum(ds.lines.values(), 'header_surcharge_amount') == Decimal('-60')
    assert _dec(ds.orders[5]['header_discount_amount']) == Decimal('100')
    assert _dec(ds.orders[5]['header_surcharge_amount']) == Decimal('-60')
    assert _dec(ds.orders[5]['net_amount']) == Decimal('-1960')


# ---------------- 4. 零基额 ----------------

def test_zero_base_blocks_confirm():
    """零基额：整单行基额为 0 时确认被拒 HEADER_DISCOUNT_ZERO_BASE。"""
    ds = _ds(lines=[_line(11, net=Decimal('0'), unit_price=0),
                    _line(12, net=Decimal('0'), unit_price=0)])
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(ds).validate_header_discount(
            {'id': 5, 'status': 'confirmed', 'header_discount_percent': 5,
             'currency_id': 8},
            old_data={'id': 5, 'status': 'draft',
                      'header_discount_percent': 0})
    assert exc.value.rule == 'HEADER_DISCOUNT_ZERO_BASE'


# ---------------- 5. 守卫 ----------------

def test_guard_rejects_invalid_header_discount():
    """守卫：率越界 / 整单折后为负 / 快照符号错误 / 非草稿改率 四类拦截。"""
    service = SalesOrderGuardService(_ds())

    with pytest.raises(SalesOrderGuardError) as exc:
        service.validate_header_discount({'id': 5,
                                          'header_discount_percent': 120})
    assert exc.value.rule == 'HEADER_DISCOUNT_RANGE'

    # 退货单（基额 -2000）叠加 50% 附加费 → 整单净额 -3000
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds(surcharge=50, category='return', lines=[
            _line(11, net=Decimal('-1000')),
            _line(12, net=Decimal('-1000')),
        ])).validate_header_discount({'id': 5,
                                      'header_surcharge_percent': 50})
    assert exc.value.rule == 'HEADER_DISCOUNT_NEGATIVE_AMOUNT'

    # 抬头折扣快照为正（应为 ≤ 0）
    with pytest.raises(SalesOrderGuardError) as exc:
        service.validate_header_discount({'id': 5,
                                          'header_discount_percent': 0,
                                          'header_discount_amount': 5})
    assert exc.value.rule == 'HEADER_DISCOUNT_NEGATIVE_AMOUNT'

    with pytest.raises(SalesOrderGuardError) as exc:
        service.validate_header_discount(
            {'id': 5, 'status': 'confirmed', 'header_discount_percent': 5},
            old_data={'id': 5, 'status': 'confirmed',
                      'header_discount_percent': 0})
    assert exc.value.rule == 'HEADER_DISCOUNT_LOCKED'


# ---------------- 6. 幂等 ----------------

def test_apply_is_idempotent():
    """幂等：同单 apply 两次，calc_results / allocation_results 行数不翻倍。"""
    ds = _ds(5, 3)
    service = SalesOrderHeaderDiscountService(ds)

    service.apply(5)
    calc_rows = len(ds.calc_results)
    alloc_rows = len(ds.allocation_results)
    order_net = _dec(ds.orders[5]['net_amount'])
    line_discount = _dec(ds.lines[11]['header_discount_amount'])
    line_surcharge = _dec(ds.lines[11]['header_surcharge_amount'])

    assert calc_rows == 4
    assert alloc_rows == 6

    service.apply(5)
    assert len(ds.calc_results) == calc_rows
    assert len(ds.allocation_results) == alloc_rows
    assert _dec(ds.orders[5]['net_amount']) == order_net
    assert _dec(ds.lines[11]['header_discount_amount']) == line_discount
    assert _dec(ds.lines[11]['header_surcharge_amount']) == line_surcharge


# ---------------- 7. 守恒 ----------------

def test_header_discount_conserves_order_net():
    """守恒：Σ 行折扣调整 = -D，Σ 行净额 = 头 calc_result 末行净额 = 抬头净额。"""
    ds = _ds(5)
    SalesOrderHeaderDiscountService(ds).apply(5)

    assert _sum(ds.lines.values(), 'header_discount_amount') == Decimal('-100')
    assert _dec(ds.lines[11]['net_amount']) == Decimal('950')
    assert _dec(ds.lines[12]['net_amount']) == Decimal('950')
    assert _dec(ds.lines[11]['tax_amount']) == Decimal('95')
    assert _dec(ds.lines[11]['gross_amount']) == Decimal('1045')

    assert _sum(ds.lines.values(), 'net_amount') == Decimal('1900')
    assert _dec(ds.orders[5]['net_amount']) == Decimal('1900')
    assert _dec(ds.orders[5]['header_discount_amount']) == Decimal('-100')

    codes = {row['code'] for row in ds.calc_results}
    assert codes == {'CR_HD_5_10', 'CR_HD_5_15', 'CR_HD_5_18', 'CR_HD_5_20'}
    last = [row for row in ds.calc_results if row['sequence'] == 20][0]
    assert _dec(last['net_amount']) == Decimal('1900')
    discount_step = [row for row in ds.calc_results
                     if row['sequence'] == 15][0]
    assert _dec(discount_step['amount']) == Decimal('-100')


# ---------------- 8. 回放 ----------------

def test_allocation_trace_replays_line_amounts():
    """回放：process_code + allocation_rule_id 两跳还原每行摊得额。"""
    ds = _ds(5, 3)
    SalesOrderHeaderDiscountService(ds).apply(5)

    heads = [r for r in ds.allocation_results if r['level'] == 'header']
    lines = [r for r in ds.allocation_results if r['level'] == 'line']
    assert len(heads) == 2
    assert len(lines) == 4

    steps = {r['sequence']: r['id'] for r in ds.calc_results
             if r['level'] == 'header'
             and r['process_code'] == 'PRICE_STD_HDR_DISC'}
    signs = {r['sequence']: r['sign'] for r in ds.calc_results
             if r['level'] == 'header'}
    assert signs[15] == '-'
    assert signs[18] == '+'

    disc_head = [r for r in heads if r['sign'] == '-'][0]
    sur_head = [r for r in heads if r['sign'] == '+'][0]

    # 第一跳：头行留痕挂头级 calc_result（parent_id 双层的外层）
    assert disc_head['parent_id'] == steps[15]
    assert sur_head['parent_id'] == steps[18]
    assert _dec(disc_head['amount']) == Decimal('100')
    assert _dec(sur_head['amount']) == Decimal('60')

    for row in ds.allocation_results:
        assert row['origin'] == 'planned'
        assert row['allocation_rule_id'] == RULE['id']
        assert row['document_type'] == 'sales_order'
        assert row['document_id'] == 5

    # 第二跳：行行留痕挂头行留痕 id
    disc_lines = [r for r in lines if r['parent_id'] == disc_head['id']]
    sur_lines = [r for r in lines if r['parent_id'] == sur_head['id']]
    assert len(disc_lines) == 2
    assert len(sur_lines) == 2

    disc_by_line = {r['document_line_id']: _dec(r['net_amount'])
                    for r in disc_lines}
    sur_by_line = {r['document_line_id']: _dec(r['net_amount'])
                   for r in sur_lines}
    assert disc_by_line == {11: Decimal('50'), 12: Decimal('50')}
    assert sur_by_line == {11: Decimal('30'), 12: Decimal('30')}

    # 留痕绝对值 + 行符号 = 业务行调整额
    for line_id in (11, 12):
        assert _dec(ds.lines[line_id]['header_discount_amount']) \
            == -disc_by_line[line_id]
        assert _dec(ds.lines[line_id]['header_surcharge_amount']) \
            == sur_by_line[line_id]


# ---------------- 9. V-B8 确认前未重算 ----------------

def test_confirm_rejected_when_header_discount_not_applied():
    """V-B8：比例已置但未 apply（行/抬头快照仍为 0）时确认被拒。"""
    ds = _ds(lines=[_line(11, net=Decimal('1000'))])
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(ds).validate_header_discount(
            {'id': 5, 'currency_id': 8, 'status': 'confirmed',
             'header_discount_percent': 5, 'header_surcharge_percent': 0,
             'header_discount_amount': 0},
            old_data={'status': 'draft'})
    assert exc.value.rule == 'HEADER_DISCOUNT_NOT_APPLIED'


def test_confirm_allowed_after_header_discount_applied():
    """V-B8 正向：快照与行调整额均为 -50（基额回算 1000）时确认放行。"""
    ds = _ds(lines=[_line(11, net=Decimal('950'))])
    ds.lines[11]['header_discount_amount'] = Decimal('-50')
    SalesOrderGuardService(ds).validate_header_discount(
        {'id': 5, 'currency_id': 8, 'status': 'confirmed',
         'header_discount_percent': 5, 'header_surcharge_percent': 0,
         'header_discount_amount': -50, 'header_surcharge_amount': 0},
        old_data={'status': 'draft'})


# ---------------- 10. V-B10 存量单据零回归 ----------------

def test_legacy_order_without_header_discount_matches_baseline():
    """V-B10：无抬头折扣的存量行，金额口径与基线一致（99.99 / 10.00 / 109.99）。"""
    line = _line(9, net=Decimal('99.99'), qty=3, unit_price=Decimal('33.33'))
    ds = _ds(lines=[line])

    values = SalesOrderAmountService(ds).recompute_line(9)
    assert values['net_amount'] == Decimal('99.99')
    assert values['tax_amount'] == Decimal('10.00')
    assert values['gross_amount'] == Decimal('109.99')
    assert _dec(ds.lines[9]['header_discount_amount']) == Decimal('0')
    assert _dec(ds.lines[9]['header_surcharge_amount']) == Decimal('0')


# ---------------- 11. V-B3 一正一退 ----------------

def test_mixed_sign_order_discount_conserves_and_scales():
    """V-B3：+1000 与 -500 两行折 10%，按有符号份额摊，Σ 行调整 = -50。

    fake 以 unit_price 为负表达退货方向（金额服务的 sign 由单据类别决定，
    整单退货会让两行同时为负，无法构造一正一退）。
    """
    ds = _ds(10, lines=[
        _line(11, net=Decimal('1000')),
        _line(12, net=Decimal('-500'), unit_price=-500),
    ])
    SalesOrderHeaderDiscountService(ds).apply(5)

    assert _dec(ds.lines[11]['header_discount_amount']) == Decimal('-100.00')
    assert _dec(ds.lines[11]['net_amount']) == Decimal('900.00')
    assert _dec(ds.lines[12]['header_discount_amount']) == Decimal('50.00')
    assert _dec(ds.lines[12]['net_amount']) == Decimal('-450.00')
    assert _sum(ds.lines.values(), 'header_discount_amount') == Decimal('-50.00')
    assert _dec(ds.orders[5]['header_discount_amount']) == Decimal('-50.00')
    assert _dec(ds.orders[5]['net_amount']) == Decimal('450.00')
