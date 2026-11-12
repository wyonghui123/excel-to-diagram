# -*- coding: utf-8 -*-
"""销售借项通知单（S8 Wave D D2 / D3）测试。

依据: docs/specs/s8-customer-invoice-wave-d/spec.md §6 / AC-6.x、§10 AC-5.2
夹具: meta/tests/factories/_customer_invoice_helpers.py（内存库，raw SQL 在工厂内）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.core.bo_action_registry import BoActionRegistry
from meta.services import customer_invoice_actions
from meta.services.bo_action_registrations import register_all_bo_actions
from meta.services.customer_invoice_service import (
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORDER_LINE_DELIVERY,
    ORG_ID,
    PAYMENT_TERM_ID,
    SHIP_LINE_ID,
    SHIPMENT_ID,
    build_conn,
    fetch_one,
    get_header,
    get_lines,
    get_schedules,
    make_ds,
    make_order,
    make_order_line,
    set_type_identity,
    shipment_billed,
    type_id,
)

DEBIT_ACTION_ID = 'customer_invoice.create_debit_memo'

DEBIT_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
    'payment_term_id': PAYMENT_TERM_ID,
}
DEBIT_LINE = {
    'description': '运费补收',
    'uom_id': 21,
    'tax_code_id': 31,
    'qty': 1,
    'unit_price': 100,
    'tax_rate': 0.13,
}


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _debit_count(conn):
    return fetch_one(conn, 'SELECT COUNT(*) AS n FROM customer_invoices')['n']


def _posted_invoice(conn):
    service = _service(conn)
    created = service.create_from_shipment(
        {'shipment_id': SHIPMENT_ID, 'invoice_date': '2026-11-09'})
    service.submit(created['id'])
    service.post(created['id'])
    return created['id']


# ---------------------------------------------------------------- D2 建单

def test_debit_action_is_registered_with_permission():
    registry = BoActionRegistry()
    register_all_bo_actions(registry)

    meta = registry.get(DEBIT_ACTION_ID)
    assert meta is not None
    assert meta.object_type == 'customer_invoice'
    assert meta.category == 'business'
    assert meta.permission_required == (
        'customer_invoice:debit_memo')
    assert meta.requires_auth is True
    assert meta.idempotent is False
    assert meta.input_schema['required'] == ['lines']


def test_create_debit_memo_creates_draft_with_sdn():
    conn = build_conn()
    created = _service(conn).create_debit_memo(dict(
        DEBIT_HEADER, reason='运费补收', lines=[DEBIT_LINE]))

    assert created['status'] == 'draft'
    assert created['invoice_no'].startswith('SDN-')
    header = get_header(conn, created['id'])
    assert int(header['document_type_id']) == type_id(conn, 'SDN')
    assert header['document_category'] == 'debit_memo'
    assert int(header['direction']) == 1
    assert header['reversal_of_invoice_id'] is None
    assert created['amounts']['gross_amount'] == 113.0

    line = get_lines(conn, created['id'])[0]
    assert line['source_doc_type'] == 'manual'
    assert line['order_line_id'] is None
    assert float(line['net_amount']) == 100.0
    assert float(line['tax_amount']) == 13.0


def test_create_debit_memo_requires_lines():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as info:
        _service(conn).create_debit_memo(dict(DEBIT_HEADER, lines=[]))

    assert info.value.rule == 'INVOICE_DEBIT_LINE_SOURCE_INVALID'
    assert _debit_count(conn) == 0


def test_create_debit_memo_fails_closed_without_default_type():
    conn = build_conn()
    set_type_identity(conn, 'SDN', status='inactive')

    with pytest.raises(CustomerInvoiceError) as info:
        _service(conn).create_debit_memo(dict(DEBIT_HEADER, lines=[DEBIT_LINE]))

    assert info.value.rule == 'INVOICE_TYPE_UNKNOWN'
    assert _debit_count(conn) == 0


def test_create_debit_memo_rejects_unknown_order_line():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as info:
        _service(conn).create_debit_memo(dict(
            DEBIT_HEADER,
            lines=[dict(DEBIT_LINE, order_line_id=999)]))

    assert info.value.rule == 'INVOICE_DEBIT_LINE_SOURCE_INVALID'
    assert info.value.field_name == 'order_line_id'
    assert _debit_count(conn) == 0


def test_create_debit_memo_rejects_cross_customer_order_line():
    conn = build_conn()
    make_order(conn, 2)
    make_order_line(conn, 21, order_id=2)

    with pytest.raises(CustomerInvoiceError) as info:
        _service(conn).create_debit_memo(dict(
            DEBIT_HEADER,
            lines=[dict(DEBIT_LINE, order_line_id=21)]))

    assert info.value.rule == 'INVOICE_DEBIT_LINE_SOURCE_INVALID'
    assert _debit_count(conn) == 0


def test_create_debit_memo_rejects_non_positive_amount():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as info:
        _service(conn).create_debit_memo(dict(
            DEBIT_HEADER,
            lines=[dict(DEBIT_LINE, unit_price=0)]))

    assert info.value.rule == 'INVOICE_LINE_AMOUNT_INVALID'
    assert _debit_count(conn) == 0


# ---------------------------------------------------------------- D3 过账

def test_debit_memo_posts_without_billed_writeback():
    conn = build_conn()
    service = _service(conn)
    created = service.create_debit_memo(dict(
        DEBIT_HEADER,
        lines=[dict(DEBIT_LINE, order_line_id=ORDER_LINE_DELIVERY)]))

    service.submit(created['id'])
    service.post(created['id'])

    header = get_header(conn, created['id'])
    assert header['status'] == 'posted'
    assert header['posting_date'] == INVOICE_DATE
    # 订单行只读引用：不消耗开票额度
    assert shipment_billed(conn) == 0.0
    assert float(fetch_one(
        conn, 'SELECT billed_qty FROM sales_order_lines WHERE id = ?',
        [ORDER_LINE_DELIVERY])['billed_qty']) == 0.0
    # 借项参与应收：按期次生成
    schedules = get_schedules(conn, created['id'])
    assert len(schedules) == 2
    assert round(sum(float(row['amount']) for row in schedules), 2) == 113.0


def test_debit_post_rejects_shipment_reference(monkeypatch):
    conn = build_conn()
    service = _service(conn)
    original = service._build_debit_line

    def injected(item, line_no, header):
        line = original(item, line_no, header)
        # 模拟历史脏数据：借项行错误引用发货行
        line['source_doc_type'] = 'shipment'
        line['shipment_line_id'] = SHIP_LINE_ID
        return line

    monkeypatch.setattr(service, '_build_debit_line', injected)
    # FR-8 行来源策略已在建单时拦截发货行；此处绕过以模拟历史脏数据，
    # 验证 D3 过账守卫仍 fail-closed（两道防线独立生效）
    monkeypatch.setattr(service, '_assert_line_source_policy', lambda *args: None)
    created = service.create_debit_memo(dict(DEBIT_HEADER, lines=[DEBIT_LINE]))
    service.submit(created['id'])

    with pytest.raises(CustomerInvoiceError) as info:
        service.post(created['id'])

    assert info.value.rule == 'INVOICE_DEBIT_BILLED_WRITEBACK_FORBIDDEN'
    assert get_header(conn, created['id'])['status'] == 'submitted'


# ---------------------------------------------------------------- AC-5.2 贷项来源角色

def test_credit_allows_debit_memo_source():
    conn = build_conn()
    service = _service(conn)
    debit = service.create_debit_memo(dict(DEBIT_HEADER, lines=[DEBIT_LINE]))
    service.submit(debit['id'])
    service.post(debit['id'])

    credit = service.create_credit_from_invoice({
        'source_invoice_id': debit['id'],
        'invoice_date': INVOICE_DATE,
        'reason': '借项冲回',
    })

    assert credit['status'] == 'draft'
    assert credit['invoice_no'].startswith('SCR-')
    header = get_header(conn, credit['id'])
    assert header['document_category'] == 'credit_memo'
    assert int(header['reversal_of_invoice_id']) == debit['id']
    assert credit['amounts']['gross_amount'] == -113.0


def test_credit_rejects_credit_memo_source():
    conn = build_conn()
    service = _service(conn)
    source_id = _posted_invoice(conn)
    credit = service.create_credit_from_invoice({
        'source_invoice_id': source_id,
        'invoice_date': INVOICE_DATE,
    })

    with pytest.raises(CustomerInvoiceError) as info:
        service.create_credit_from_invoice({
            'source_invoice_id': credit['id'],
            'invoice_date': INVOICE_DATE,
        })

    assert info.value.rule == 'INVOICE_CREDIT_SOURCE_ROLE_INVALID'
    assert info.value.field_name == 'source_invoice_id'