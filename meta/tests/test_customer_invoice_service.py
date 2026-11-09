# -*- coding: utf-8 -*-
"""销售发票服务测试（S8 Wave A）—— 建单 / 提交 / 过账 / 红冲 / 派生回写。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §8.1（服务 14 条）
夹具: meta/tests/factories/_customer_invoice_helpers.py（内存库，raw SQL 在工厂内）
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import (
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORDER_ID,
    ORDER_LINE_DELIVERY,
    ORG_ID,
    SHIPMENT_ID,
    SHIP_LINE_ID,
    build_conn,
    get_header,
    get_lines,
    get_schedules,
    make_ds,
    set_header_amounts,
    set_order_line_billed,
    set_shipment_line_billed,
    set_shipment_status,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
}


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _from_shipment(conn, **overrides):
    payload = dict(BASE_HEADER, shipment_id=SHIPMENT_ID)
    payload.update(overrides)
    return _service(conn).create_from_shipment(payload)


def _expect(error, rule):
    assert isinstance(error.value, CustomerInvoiceError)
    assert error.value.rule == rule
    return error.value


# ---------------------------------------------------------------- 建单

def test_create_from_shipment_takes_number_and_snapshots_lines():
    conn = build_conn()
    result = _from_shipment(conn)

    assert result['invoice_no'] == 'SINV-202611-00001'
    assert result['status'] == 'draft'
    assert result['amounts'] == {'net_amount': 500.0, 'tax_amount': 65.0,
                                 'gross_amount': 565.0}
    lines = get_lines(conn, result['id'])
    assert [line['shipment_line_id'] for line in lines] == [81, 82]
    first = lines[0]
    assert first['source_doc_type'] == 'shipment'
    assert first['order_line_id'] == ORDER_LINE_DELIVERY
    assert first['billing_basis'] == 'quantity'
    assert first['price_source'] == 'order'
    assert Decimal(str(first['qty'])) == Decimal('40')
    assert Decimal(str(first['net_amount'])) == Decimal('400')


def test_create_from_shipment_partial_qty():
    conn = build_conn()
    result = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 15}])

    lines = get_lines(conn, result['id'])
    assert len(lines) == 1
    assert Decimal(str(lines[0]['qty'])) == Decimal('15')
    assert Decimal(str(lines[0]['gross_amount'])) == Decimal('169.5')
    assert result['amounts']['gross_amount'] == 169.5


def test_create_from_shipment_rejects_qty_over_available():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _from_shipment(
            conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 41}])
    _expect(error, 'INVOICE_QTY_EXCEEDED')


def test_create_from_shipment_requires_shipped_state():
    conn = build_conn()
    set_shipment_status(conn, 'staged')
    with pytest.raises(CustomerInvoiceError) as error:
        _from_shipment(conn)
    _expect(error, 'INVOICE_SHIPMENT_STATE_INVALID')


def test_create_from_shipment_rejects_when_all_billed():
    conn = build_conn()
    set_shipment_line_billed(conn, 40)
    set_shipment_line_billed(conn, 10, line_id=82)
    with pytest.raises(CustomerInvoiceError) as error:
        _from_shipment(conn)
    _expect(error, 'INVOICE_SOURCE_INVALID')


def test_create_manual_amount_line_derives_unit_price():
    conn = build_conn()
    result = _service(conn).create_manual(dict(
        BASE_HEADER,
        lines=[{'description': '咨询服务', 'uom_id': 21, 'tax_code_id': 31,
                'tax_rate_percent': 6, 'billing_basis': 'amount',
                'net_amount': 1000}]))

    line = get_lines(conn, result['id'])[0]
    assert line['source_doc_type'] == 'manual'
    assert line['price_source'] == 'manual'
    assert Decimal(str(line['qty'])) == Decimal('1')
    assert Decimal(str(line['unit_price'])) == Decimal('1000')
    assert Decimal(str(line['tax_amount'])) == Decimal('60')
    assert result['amounts']['gross_amount'] == 1060.0


def test_create_manual_line_requires_tax_code():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER,
            lines=[{'description': '缺税码', 'uom_id': 21,
                    'tax_rate_percent': 6, 'net_amount': 100}]))
    _expect(error, 'INVOICE_SOURCE_INVALID')


def test_create_manual_plan_schedule_fails_closed():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'schedule_id': 72}]))
    _expect(error, 'INVOICE_RELEVANCE_NOT_SUPPORTED')


def test_order_line_plan_relevance_fails_closed():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'order_line_id': 12, 'qty': 5}]))
    _expect(error, 'INVOICE_RELEVANCE_NOT_SUPPORTED')


def test_order_line_none_relevance_rejected():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'order_line_id': 13, 'qty': 5}]))
    _expect(error, 'INVOICE_SOURCE_MISMATCH')


def test_line_source_keys_are_mutually_exclusive():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER,
            lines=[{'shipment_line_id': SHIP_LINE_ID,
                    'order_line_id': ORDER_LINE_DELIVERY, 'qty': 1}]))
    _expect(error, 'INVOICE_LINE_XOR')


def test_manual_order_line_invoice_uses_order_price():
    conn = build_conn()
    result = _service(conn).create_manual(dict(
        BASE_HEADER,
        lines=[{'order_line_id': ORDER_LINE_DELIVERY, 'qty': 30}]))

    line = get_lines(conn, result['id'])[0]
    assert line['source_doc_type'] == 'sales_order'
    assert line['shipment_line_id'] is None
    assert Decimal(str(line['net_amount'])) == Decimal('300')
    assert result['amounts']['gross_amount'] == 339.0


# ---------------------------------------------------------------- 提交 / 过账

def test_submit_requires_lines():
    conn = build_conn()
    service = _service(conn)
    header = service.prepare_header(dict(BASE_HEADER))
    invoice_id = service._insert_header(header)

    with pytest.raises(CustomerInvoiceError) as error:
        service.submit(invoice_id)
    _expect(error, 'INVOICE_SOURCE_INVALID')


def test_submit_rejects_exhausted_source_after_other_invoice_posted():
    conn = build_conn()
    service = _service(conn)
    first = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 40}])
    second = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 10}])

    service.submit(first['id'])
    service.post(first['id'])
    with pytest.raises(CustomerInvoiceError) as error:
        service.submit(second['id'])
    _expect(error, 'INVOICE_QTY_EXCEEDED')


def test_post_writes_progress_schedules_and_order_billing():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    service.submit(result['id'])

    posted = service.post(result['id'], posting_date=INVOICE_DATE)

    assert posted['status'] == 'posted'
    header = get_header(conn, result['id'])
    assert header['status'] == 'posted'
    assert header['posting_date'] == INVOICE_DATE
    shipment_billed = conn.execute(
        'SELECT billed_qty FROM shipment_lines WHERE id = ?',
        [SHIP_LINE_ID]).fetchone()[0]
    assert Decimal(str(shipment_billed)) == Decimal('40')
    order_line = conn.execute(
        'SELECT billed_qty FROM sales_order_lines WHERE id = ?',
        [ORDER_LINE_DELIVERY]).fetchone()
    assert Decimal(str(order_line[0])) == Decimal('50')
    order = conn.execute(
        'SELECT billing_status FROM sales_orders WHERE id = ?',
        [ORDER_ID]).fetchone()
    assert order[0] == 'partial'
    schedules = get_schedules(conn, result['id'])
    assert len(schedules) == 2
    assert Decimal(str(schedules[0]['amount'])) == Decimal('169.5')
    assert Decimal(str(schedules[1]['amount'])) == Decimal('395.5')


def test_post_rejects_second_time():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    service.submit(result['id'])
    service.post(result['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.post(result['id'])
    _expect(error, 'INVOICE_STATE_INVALID')


def test_post_rejects_posting_date_before_invoice_date():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    service.submit(result['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.post(result['id'], posting_date='2026-11-01')
    _expect(error, 'INVOICE_POSTING_DATE_INVALID')


def test_post_rejects_tampered_header_totals():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    set_header_amounts(conn, result['id'], gross=999.0)
    service.submit(result['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.post(result['id'])
    _expect(error, 'INVOICE_AMOUNT_MISMATCH')


def test_recompute_order_billing_full_when_all_lines_billed():
    conn = build_conn()
    for line_id, qty in ((11, 100), (12, 50), (13, 5)):
        set_order_line_billed(conn, line_id, qty)

    result = _service(conn).recompute_order_billing(ORDER_ID)

    assert result['billing_status'] == 'full'
    order = conn.execute(
        'SELECT billing_status, billing_derived_at FROM sales_orders '
        'WHERE id = ?', [ORDER_ID]).fetchone()
    assert order[0] == 'full'
    assert order[1]


def test_cancel_draft_then_transitions_rejected():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)

    service.cancel(result['id'])
    assert get_header(conn, result['id'])['status'] == 'cancelled'
    with pytest.raises(CustomerInvoiceError) as error:
        service.submit(result['id'])
    _expect(error, 'INVOICE_STATE_INVALID')


# ---------------------------------------------------------------- 红冲

def _posted_invoice(conn):
    service = _service(conn)
    result = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 40}])
    service.submit(result['id'])
    service.post(result['id'])
    return service, result


def test_reverse_creates_red_invoice_and_rolls_back_progress():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    reversed_result = service.reverse(original['id'], '客户退货')

    assert reversed_result['red_invoice_no'] == 'SCR-202611-00001'
    assert reversed_result['status'] == 'reversed'
    assert get_header(conn, original['id'])['status'] == 'reversed'
    red = get_header(conn, reversed_result['red_invoice_id'])
    assert red['status'] == 'posted'
    assert red['reversal_of_invoice_id'] == original['id']
    assert Decimal(str(red['gross_amount'])) == Decimal('-452')
    red_lines = get_lines(conn, red['id'])
    assert Decimal(str(red_lines[0]['qty'])) == Decimal('-40')
    assert red_lines[0]['original_invoice_line_id']
    assert Decimal(str(conn.execute(
        'SELECT billed_qty FROM shipment_lines WHERE id = ?',
        [SHIP_LINE_ID]).fetchone()[0])) == Decimal('0')
    assert Decimal(str(conn.execute(
        'SELECT billed_qty FROM sales_order_lines WHERE id = ?',
        [ORDER_LINE_DELIVERY]).fetchone()[0])) == Decimal('0')
    assert conn.execute(
        'SELECT billing_status FROM sales_orders WHERE id = ?',
        [ORDER_ID]).fetchone()[0] == 'none'
    cancelled = get_schedules(conn, original['id'])
    assert [row['status'] for row in cancelled] == ['cancelled', 'cancelled']
    assert get_schedules(conn, red['id']) == []


def test_reverse_rejects_second_red_invoice():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    service.reverse(original['id'], '第一次红冲')

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(original['id'], '重复红冲')
    _expect(error, 'INVOICE_REVERSE_EXISTS')


def test_reverse_requires_reason():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(original['id'], '  ')
    _expect(error, 'INVOICE_REVERSE_INVALID')
