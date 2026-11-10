# -*- coding: utf-8 -*-
"""销售发票金额精度与分摊守恒测试。

依据:
  docs/specs/sales-invoice-pricing-spec-2026-11-10.md FR-006 / FR-011 / NFR-005
  §9.3.2「精度唯一真源 = currencies.decimal_places，统一经 round_amount 舍入」

覆盖:
  1. 币种精度（JPY 0 位 / CNY 2 位）对行净额、税额、含税金额的落库舍入；
  2. 税额税基 = 已舍入净额（不是未舍入的 qty × unit_price）；
  3. 部分发货按数量比例拆分订单行净额与抬头折扣/附加费，多张发票合计不重不漏；
  4. 发票头金额 = Σ 行金额；行级舍入残差按币种精度落库，不作为抬头差额留存。
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import CustomerInvoiceService
from meta.tests.factories._customer_invoice_helpers import (
    BILLING_SCHEDULE_ID,
    CURRENCY_ID,
    INVOICE_DATE,
    ORDER_LINE_DELIVERY,
    ORDER_LINE_PLAN,
    SHIPMENT_ID,
    SHIP_LINE_ID,
    SHIP_LINE_SECOND,
    add_currency,
    add_tax_code,
    build_conn,
    get_header,
    get_lines,
    get_schedules,
    make_ds,
    set_order_line_amounts,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': 900,
    'currency_id': CURRENCY_ID,
    'org_id': 10,
}

JPY_ID = 2


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _manual_line(**overrides):
    line = {'description': '精密设备', 'uom_id': 21, 'tax_code_id': 31,
            'tax_rate_percent': 13, 'billing_basis': 'quantity',
            'qty': 3, 'unit_price': 1234.5678}
    line.update(overrides)
    return line


def _dec(value):
    return Decimal(str(value))


def _sum_net(lines):
    return sum(_dec(line['net_amount']) for line in lines)


# ---------------------------------------------------------------- 币种精度

def test_jpy_zero_decimals_rounds_net_and_tax_from_rounded_net():
    """JPY 0 位：3 × 1234.5678 = 3703.7034 → 3704；税额按已舍入净额计算。"""
    conn = build_conn()
    add_currency(conn, JPY_ID, 'JPY', 0)
    result = _service(conn).create_manual(dict(
        BASE_HEADER, currency_id=JPY_ID, lines=[_manual_line()]))

    line = get_lines(conn, result['id'])[0]
    assert _dec(line['net_amount']) == Decimal('3704')
    # 若税基用未舍入净额 3703.7034 × 13% → 481，说明税基未跟随币种精度
    assert _dec(line['tax_amount']) == Decimal('482')
    assert _dec(line['gross_amount']) == Decimal('4186')

    assert result['amounts'] == {'net_amount': 3704.0, 'tax_amount': 482.0,
                                 'gross_amount': 4186.0}
    header = get_header(conn, result['id'])
    # 行级残差 3703.7034 - 3704 = -0.2966 低于 JPY 最小单位（1），
    # rounding_diff 按币种精度落库后归 0，恒等式 gross = net + tax + diff 成立
    assert _dec(header['rounding_diff']) == Decimal('0')


def test_cny_two_decimals_rounds_net_and_tax():
    """CNY 2 位：3 × 1234.5678 = 3703.7034 → 3703.70；税额 481.48。"""
    conn = build_conn()
    result = _service(conn).create_manual(dict(
        BASE_HEADER, lines=[_manual_line()]))

    line = get_lines(conn, result['id'])[0]
    assert _dec(line['net_amount']) == Decimal('3703.70')
    assert _dec(line['tax_amount']) == Decimal('481.48')
    assert _dec(line['gross_amount']) == Decimal('4185.18')
    assert result['amounts'] == {'net_amount': 3703.7, 'tax_amount': 481.48,
                                 'gross_amount': 4185.18}
    header = get_header(conn, result['id'])
    # 行级残差 0.0034 低于 CNY 最小单位（0.01），舍入后归 0
    assert _dec(header['rounding_diff']) == Decimal('0')


# ---------------------------------------------------------------- 分摊守恒

def test_partial_shipments_apportion_order_line_amounts_without_gaps():
    """订单行净额 1050（含抬头折扣 -100 / 附加费 +150），50/100 分两次开票。

    期望：两张发票合计净额 525，剩余 525 留给后续开票，不重不漏；
    抬头折扣 / 附加费同样按数量比例拆分。
    """
    conn = build_conn()
    set_order_line_amounts(conn, ORDER_LINE_DELIVERY, net=1050,
                           discount=-100, surcharge=150)
    service = _service(conn)

    first = service.create_from_shipment(dict(
        BASE_HEADER, shipment_id=SHIPMENT_ID,
        lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 25}]))
    second = service.create_from_shipment(dict(
        BASE_HEADER, shipment_id=SHIPMENT_ID,
        lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 15},
               {'shipment_line_id': SHIP_LINE_SECOND, 'qty': 10}]))

    for invoice in (first, second):
        lines = get_lines(conn, invoice['id'])
        header = get_header(conn, invoice['id'])
        # 抬头金额 = Σ 行金额
        assert _dec(header['net_amount']) == _sum_net(lines) == Decimal('262.50')
        assert _dec(header['tax_amount']) == Decimal('34.13')
        assert _dec(header['gross_amount']) == Decimal('296.63')
        # 分摊额与快照净额自洽：舍入差为 0
        assert _dec(header['rounding_diff']) == Decimal('0')
        assert sum(_dec(line['header_discount_amount']) for line in lines) \
            == Decimal('-25.00')
        assert sum(_dec(line['header_surcharge_amount']) for line in lines) \
            == Decimal('37.50')

    billed = _dec(first['amounts']['net_amount']) + _dec(
        second['amounts']['net_amount'])
    assert billed == Decimal('525.00')
    # 该订单行总净额 1050，未开票部分仍为 525（50/100 数量）
    assert Decimal('1050') - billed == Decimal('525')


def test_partial_shipment_net_uses_order_snapshot_not_rebuilt_price():
    """回归 P0：部分发货取订单行净额快照，不按 qty × unit_price 重建。

    订单行 net_amount=900（含 -100 抬头折扣），发 25/100 → 净额 225；
    若按 25 × 10 重建会得到 250（多计 25 折扣）。
    """
    conn = build_conn()
    set_order_line_amounts(conn, ORDER_LINE_DELIVERY, net=900, discount=-100)
    result = _service(conn).create_from_shipment(dict(
        BASE_HEADER, shipment_id=SHIPMENT_ID,
        lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 25}]))

    line = get_lines(conn, result['id'])[0]
    assert _dec(line['net_amount']) == Decimal('225.00')
    assert _dec(line['header_discount_amount']) == Decimal('-25.00')
    assert _dec(line['unit_price']) == Decimal('10')
    assert _dec(get_header(conn, result['id'])['rounding_diff']) == Decimal('0')


# ---------------------------------------------------------------- 税舍入方向

def test_tax_rounding_direction_from_tax_code_ceil():
    """税码 rounding=ceil：净额 100.10 × 13% = 13.013 → 13.02（方向唯一真源）。"""
    conn = build_conn()
    add_tax_code(conn, 77, 'CEIL13', 'ceil')
    result = _service(conn).create_manual(dict(
        BASE_HEADER, lines=[_manual_line(
            tax_code_id=77, qty=1, unit_price=100.10)]))

    line = get_lines(conn, result['id'])[0]
    assert _dec(line['net_amount']) == Decimal('100.10')
    assert _dec(line['tax_amount']) == Decimal('13.02')
    assert _dec(line['gross_amount']) == Decimal('113.12')


# ---------------------------------------------------------------- 期次精度

def test_jpy_payment_schedule_rounds_to_currency_precision_tail_on_last():
    """JPY 0 位：价税合计 113001 按 40/30/30 分摊 → 45200 / 33900 / 33901。"""
    conn = build_conn(payment_term_lines=(
        (1, 40, 0, None, 0), (2, 30, 0, None, 0), (3, 30, 0, None, 0)))
    add_currency(conn, JPY_ID, 'JPY', 0)
    service = _service(conn)
    created = service.create_manual(dict(
        BASE_HEADER, currency_id=JPY_ID, payment_term_id=5,
        lines=[_manual_line(qty=1, unit_price=100001)]))
    service.submit(created['id'])
    service.post(created['id'])

    amounts = [int(_dec(row['amount']))
               for row in get_schedules(conn, created['id'])]
    # 前两期按比例舍入（45200.4→45200、33900.3→33900），尾差 1 归最后一期
    assert amounts == [45200, 33900, 33901]
    assert sum(amounts) == 113001


# ---------------------------------------------------------------- 计划行分摊

def test_plan_line_carries_order_header_allocation_detail():
    """计划行按比例继承订单行抬头折扣/附加费；Σ 行 = 抬头，1×单价+分摊 = 净额。"""
    conn = build_conn()
    set_order_line_amounts(conn, ORDER_LINE_PLAN, net=1000,
                           discount=-100, surcharge=50)
    created = _service(conn).create_from_schedule(dict(
        BASE_HEADER, schedule_ids=[BILLING_SCHEDULE_ID]))

    line = get_lines(conn, created['id'])[0]
    header = get_header(conn, created['id'])
    assert _dec(line['net_amount']) == Decimal('1000.00')
    assert _dec(line['header_discount_amount']) == Decimal('-100.00')
    assert _dec(line['header_surcharge_amount']) == Decimal('50.00')
    assert (_dec(line['qty']) * _dec(line['unit_price'])
            + _dec(line['header_discount_amount'])
            + _dec(line['header_surcharge_amount'])) == _dec(line['net_amount'])
    # 抬头 = Σ 行（唯一聚合入口）
    assert _dec(header['header_discount_amount']) == Decimal('-100.00')
    assert _dec(header['header_surcharge_amount']) == Decimal('50.00')
    assert _dec(header['rounding_diff']) == Decimal('0')