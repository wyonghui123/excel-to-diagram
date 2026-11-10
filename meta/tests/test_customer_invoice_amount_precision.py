# -*- coding: utf-8 -*-
"""销售发票金额精度与分摊守恒测试。

依据:
  docs/specs/sales-invoice-pricing-spec-2026-11-10.md FR-006 / FR-011 / NFR-005
  §9.3.2「精度唯一真源 = currencies.decimal_places，统一经 round_amount 舍入」

覆盖:
  1. 币种精度（JPY 0 位 / CNY 2 位）对行净额、税额、含税金额的落库舍入；
  2. 税额税基 = 已舍入净额（不是未舍入的 qty × unit_price）；
  3. 部分发货按数量比例拆分订单行净额与抬头折扣/附加费，多张发票合计不重不漏；
  4. 发票头金额 = Σ 行金额，舍入差留痕在 rounding_diff。
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import CustomerInvoiceService
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    INVOICE_DATE,
    ORDER_LINE_DELIVERY,
    SHIPMENT_ID,
    SHIP_LINE_ID,
    SHIP_LINE_SECOND,
    add_currency,
    build_conn,
    get_header,
    get_lines,
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
    # 舍入差 = 算术重建净额 - 落库净额 = 3703.7034 - 3704
    assert _dec(header['rounding_diff']) == Decimal('-0.2966')


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
    assert _dec(header['rounding_diff']) == Decimal('0.0034')


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