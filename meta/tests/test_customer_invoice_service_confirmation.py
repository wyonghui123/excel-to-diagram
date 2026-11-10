# -*- coding: utf-8 -*-
"""服务确认开票测试（TBD-11 A）—— 已兑现服务期次 → 发票。

依据:
  docs/specs/sales-invoice-pricing-spec-2026-11-10.md §11.3.3 缺口①
  事实源: sales_order_schedules(schedule_kind='service', status='completed')
  口径: 确认量 × 订单行单价；上限 = 期次金额 − 已开票金额
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import (
    SERVICE_DOC_FLOW_RULE_ID,
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORDER_LINE_DELIVERY,
    ORDER_LINE_PLAN,
    ORG_ID,
    make_billing_schedule,
    make_ds,
    make_order,
    make_order_line,
    build_conn,
    fetch_one,
    get_lines,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
}

SERVICE_SCHEDULE_ID = 81
#: 订单行 12：数量 50、单价 20、净额 1000 → 服务期次 5 × 20 = 100
SERVICE_QTY = 5
SERVICE_UNIT_PRICE = Decimal('20')


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _make_service_schedule(conn, schedule_id=SERVICE_SCHEDULE_ID, **overrides):
    params = {
        'kind': 'service',
        'status': 'completed',
        'promised_qty': SERVICE_QTY,
    }
    params.update(overrides)
    make_billing_schedule(conn, schedule_id, **params)


def _from_service(conn, **overrides):
    payload = dict(BASE_HEADER, schedule_ids=[SERVICE_SCHEDULE_ID])
    payload.update(overrides)
    return _service(conn).create_from_service_confirmation(payload)


def _expect(error, rule):
    assert isinstance(error.value, CustomerInvoiceError)
    assert error.value.rule == rule
    return error.value


def _schedule_row(conn, schedule_id=SERVICE_SCHEDULE_ID):
    return fetch_one(
        conn, 'SELECT * FROM sales_order_schedules WHERE id = ?',
        [schedule_id])


def _order_line_row(conn, line_id=ORDER_LINE_PLAN):
    return fetch_one(conn, 'SELECT * FROM sales_order_lines WHERE id = ?',
                     [line_id])


def test_create_from_service_confirmation_builds_quantity_line():
    conn = build_conn()
    _make_service_schedule(conn)

    result = _from_service(conn)

    assert result['status'] == 'draft'
    assert result['amounts']['net_amount'] == 100.0
    line = get_lines(conn, result['id'])[0]
    assert line['source_doc_type'] == 'service_confirmation'
    assert line['schedule_id'] == SERVICE_SCHEDULE_ID
    assert line['order_line_id'] is None
    assert line['billing_basis'] == 'quantity'
    assert Decimal(str(line['qty'])) == Decimal('5')
    assert Decimal(str(line['unit_price'])) == SERVICE_UNIT_PRICE
    assert Decimal(str(line['net_amount'])) == Decimal('100')
    assert Decimal(str(line['billing_base_amount'])) == Decimal('100')
    assert line['billing_percent'] is None
    assert line['price_source'] == 'order'


def test_create_from_service_confirmation_accepts_partial_qty():
    conn = build_conn()
    _make_service_schedule(conn)

    result = _from_service(conn, lines=[{
        'schedule_id': SERVICE_SCHEDULE_ID, 'qty': 2}])

    line = get_lines(conn, result['id'])[0]
    assert Decimal(str(line['qty'])) == Decimal('2')
    assert Decimal(str(line['net_amount'])) == Decimal('40')


def test_create_from_service_confirmation_rejects_unconfirmed_period():
    conn = build_conn()
    _make_service_schedule(conn, status='planned')

    with pytest.raises(CustomerInvoiceError) as error:
        _from_service(conn)
    _expect(error, 'INVOICE_SERVICE_STATE_INVALID')


def test_create_from_service_confirmation_rejects_non_service_kind():
    conn = build_conn()
    make_billing_schedule(conn, 82, percent=100)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_service(conn, schedule_ids=[82])
    _expect(error, 'INVOICE_SERVICE_STATE_INVALID')


def test_create_from_service_confirmation_rejects_non_plan_line():
    conn = build_conn()
    _make_service_schedule(conn, line_id=ORDER_LINE_DELIVERY)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_service(conn)
    _expect(error, 'INVOICE_RELEVANCE_NOT_PLAN')


def test_create_from_service_confirmation_rejects_mixed_orders():
    conn = build_conn()
    _make_service_schedule(conn)
    make_order(conn, 2)
    make_order_line(conn, 21, order_id=2, relevance='plan', net_amount=500)
    make_billing_schedule(conn, 83, order_id=2, line_id=21, kind='service',
                          status='completed', promised_qty=1)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_service(conn, schedule_ids=[SERVICE_SCHEDULE_ID, 83])
    _expect(error, 'INVOICE_SERVICE_ORDER_MISMATCH')


def test_create_from_service_confirmation_rejects_over_remaining():
    conn = build_conn()
    _make_service_schedule(conn, billed_amount=80)

    # 剩余 20，显式确认 5 个 → 100，超过剩余金额
    with pytest.raises(CustomerInvoiceError) as error:
        _from_service(conn, lines=[{
            'schedule_id': SERVICE_SCHEDULE_ID, 'qty': 5}])
    _expect(error, 'INVOICE_SERVICE_EXCEEDED')


def test_create_from_service_confirmation_rejects_duplicate_lines():
    conn = build_conn()
    _make_service_schedule(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_service(conn, lines=[
            {'schedule_id': SERVICE_SCHEDULE_ID, 'qty': 3},
            {'schedule_id': SERVICE_SCHEDULE_ID, 'qty': 3},
        ])
    _expect(error, 'INVOICE_SERVICE_EXCEEDED')


def test_post_service_confirmation_writes_back_billed_amount():
    conn = build_conn()
    _make_service_schedule(conn)
    service = _service(conn)
    created = _from_service(conn)

    service.submit(created['id'])
    service.post(created['id'], posting_date=INVOICE_DATE)

    schedule = _schedule_row(conn)
    assert Decimal(str(schedule['billed_amount'])) == Decimal('100')
    assert schedule['billing_status'] == 'full'


def test_reverse_service_confirmation_rolls_back_billed_amount():
    conn = build_conn()
    _make_service_schedule(conn)
    service = _service(conn)
    created = _from_service(conn)
    service.submit(created['id'])
    service.post(created['id'], posting_date=INVOICE_DATE)

    service.reverse(created['id'], '服务取消')

    schedule = _schedule_row(conn)
    assert Decimal(str(schedule['billed_amount'])) == Decimal('0')
    assert schedule['billing_status'] == 'none'


def test_service_confirmation_writes_own_doc_flow_edge(monkeypatch):
    calls = []

    def _fake_attach_edge(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    monkeypatch.setattr('meta.core.doc_flow_attach.attach_edge',
                        _fake_attach_edge)
    conn = build_conn()
    _make_service_schedule(conn)
    service = _service(conn)
    created = _from_service(conn)

    service.submit(created['id'])
    service.post(created['id'], posting_date=INVOICE_DATE)

    line = get_lines(conn, created['id'])[0]
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[2] == SERVICE_DOC_FLOW_RULE_ID
    assert args[3] == SERVICE_SCHEDULE_ID
    assert args[4] == line['id']
    assert kwargs['amount'] == 100.0


def test_service_confirmation_line_source_policy_allows_source():
    """YAML line_source_policy.invoice 必须允许 service_confirmation。"""
    conn = build_conn()
    _make_service_schedule(conn)

    # 若策略缺该来源，_insert_lines 会抛 INVOICE_LINE_SOURCE_POLICY_VIOLATION
    result = _from_service(conn)
    assert result['status'] == 'draft'